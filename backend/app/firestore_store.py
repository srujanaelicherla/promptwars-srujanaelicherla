"""Firestore repositories. Matching and fairness code does not import this module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4

from google.api_core.exceptions import Aborted, DeadlineExceeded
from google.cloud import firestore
from pydantic import BaseModel

from app.bookings import (
    ACTIVE_STATUSES,
    BookingError,
    BookingStore,
    RESTRICTED_MESSAGE,
    _require_future_range,
    lookup_equipment,
    lookup_project,
    resolve_project_id,
)
from app.access import AccessStore
from app.authn import require_faculty_scope
from app.models import (
    AccessRequest,
    AllocationDecision,
    Approval,
    ApprovalDecision,
    Booking,
    BookingStatus,
    Department,
    Equipment,
    EquipmentStatus,
    Lab,
    OfferStatus,
    Project,
    RequestStatus,
    Role,
    SlotOffer,
    User,
    WaitlistEntry,
    WaitlistStatus,
)
from app.seed import Catalog
from app.slots import slot_keys
from app.users import UserStore
from app.waitlist import WaitlistStore

_T = TypeVar("_T", bound=BaseModel)
_RETRYABLE = (Aborted, DeadlineExceeded)
_MAX_ATTEMPTS = 5


def _dump(model: BaseModel) -> dict[str, object]:
    return json.loads(model.model_dump_json())


def _load(model_type: type[_T], data: dict[str, object] | None) -> _T:
    if data is None:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    payload = {key: value for key, value in data.items() if key in model_type.model_fields}
    return model_type.model_validate(payload)


class FirestoreUserStore(UserStore):
    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._col = client.collection("users")

    def get(self, user_id: str) -> User | None:
        snap = self._col.document(user_id).get()
        if not snap.exists:
            return None
        return _load(User, snap.to_dict())

    def upsert(self, user: User) -> None:
        payload = _dump(user)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._col.document(user.id).set(payload, merge=True)

    def snapshot(self) -> list[User]:
        return [_load(User, snap.to_dict()) for snap in self._col.stream()]


class FirestoreBookingStore(BookingStore):
    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._bookings = client.collection("bookings")
        self._locks = client.collection("slot_locks")
        self._equipment = client.collection("equipment")

    def snapshot(self) -> list[Booking]:
        return [_load(Booking, snap.to_dict()) for snap in self._bookings.stream()]

    def for_user(self, user_id: str) -> list[Booking]:
        query = self._bookings.where("user_id", "==", user_id)
        return [_load(Booking, snap.to_dict()) for snap in query.stream()]

    def create(
        self,
        *,
        catalog: Catalog,
        equipment_id: str,
        project_id: str,
        start: datetime,
        end: datetime,
        now: datetime,
        user_id: str,
        prerequisites_verified: bool = False,
        purpose: str = "",
    ) -> Booking:
        _require_future_range(start, end, now=now)
        equipment = lookup_equipment(catalog, equipment_id)
        resolved_project = resolve_project_id(catalog, equipment, project_id)
        if equipment.status is not EquipmentStatus.AVAILABLE:
            raise BookingError(409, "unavailable", "This item is not operational.")
        if equipment.safety_prerequisites and not prerequisites_verified:
            raise BookingError(403, "restricted", RESTRICTED_MESSAGE)
        keys = slot_keys(equipment.id, start, end)
        last_error: Exception | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                return self._create_in_transaction(
                    equipment_id=equipment.id,
                    project_id=resolved_project,
                    start=start,
                    end=end,
                    user_id=user_id,
                    keys=keys,
                    purpose=purpose.strip()[:200],
                )
            except _RETRYABLE as exc:
                last_error = exc
                continue
        raise BookingError(503, "request_failed", "The booking could not be completed.") from last_error

    def _create_in_transaction(
        self,
        *,
        equipment_id: str,
        project_id: str,
        start: datetime,
        end: datetime,
        user_id: str,
        keys: tuple[str, ...],
        purpose: str = "",
    ) -> Booking:
        transaction = self._client.transaction()
        booking_id = f"book-{uuid4().hex}"
        booking_ref = self._bookings.document(booking_id)
        equipment_ref = self._equipment.document(equipment_id)
        lock_refs = [self._locks.document(key) for key in keys]

        @firestore.transactional
        def run(txn: firestore.Transaction) -> Booking:
            equipment_snap = equipment_ref.get(transaction=txn)
            if not equipment_snap.exists:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            equipment = _load(Equipment, equipment_snap.to_dict())
            if equipment.status is not EquipmentStatus.AVAILABLE:
                raise BookingError(409, "unavailable", "This item is not operational.")
            for ref in lock_refs:
                lock_snap = ref.get(transaction=txn)
                if lock_snap.exists:
                    raise BookingError(409, "conflict", "This slot overlaps an existing booking.")
            booking = Booking(
                id=booking_id,
                user_id=user_id,
                equipment_id=equipment_id,
                project_id=project_id,
                start=start,
                end=end,
                status=BookingStatus.APPROVED,
                purpose=purpose,
            )
            txn.set(booking_ref, _dump(booking))
            for key, ref in zip(keys, lock_refs, strict=True):
                txn.set(
                    ref,
                    {
                        "equipment_id": equipment_id,
                        "booking_id": booking_id,
                        "slot_key": key,
                        "status": "held",
                    },
                )
            return booking

        return run(transaction)

    def cancel(self, *, booking_id: str, actor: User) -> Booking:
        from app.models import Role

        snap = self._bookings.document(booking_id).get()
        if not snap.exists:
            raise BookingError(404, "not_found", "The requested resource does not exist.")
        current = _load(Booking, snap.to_dict())
        if current.user_id != actor.id and actor.role is not Role.ADMIN:
            raise BookingError(403, "forbidden", "This identity cannot cancel that booking.")
        if current.status not in ACTIVE_STATUSES:
            raise BookingError(409, "conflict", "This booking is not active.")
        keys = slot_keys(current.equipment_id, current.start, current.end)
        transaction = self._client.transaction()
        booking_ref = self._bookings.document(booking_id)
        lock_refs = [self._locks.document(key) for key in keys]

        @firestore.transactional
        def run(txn: firestore.Transaction) -> Booking:
            live = _load(Booking, booking_ref.get(transaction=txn).to_dict())
            if live.status not in ACTIVE_STATUSES:
                raise BookingError(409, "conflict", "This booking is not active.")
            lock_snaps = [ref.get(transaction=txn) for ref in lock_refs]
            updated = live.model_copy(update={"status": BookingStatus.CANCELLED})
            txn.set(booking_ref, _dump(updated))
            for ref, lock_snap in zip(lock_refs, lock_snaps, strict=True):
                data = lock_snap.to_dict() if lock_snap.exists else None
                if data and data.get("booking_id") == booking_id:
                    txn.delete(ref)
            return updated

        return run(transaction)

    def acquire_hold(
        self,
        *,
        catalog: Catalog,
        equipment_id: str,
        start: datetime,
        end: datetime,
        now: datetime,
        offer_id: str,
    ) -> None:
        _require_future_range(start, end, now=now)
        lookup_equipment(catalog, equipment_id)
        keys = slot_keys(equipment_id, start, end)
        last_error: Exception | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                self._hold_in_transaction(equipment_id=equipment_id, keys=keys, offer_id=offer_id)
                return
            except _RETRYABLE as exc:
                last_error = exc
                continue
        raise BookingError(503, "request_failed", "The offer hold could not be completed.") from last_error

    def _hold_in_transaction(self, *, equipment_id: str, keys: tuple[str, ...], offer_id: str) -> None:
        transaction = self._client.transaction()
        equipment_ref = self._equipment.document(equipment_id)
        lock_refs = [self._locks.document(key) for key in keys]

        @firestore.transactional
        def run(txn: firestore.Transaction) -> None:
            equipment_snap = equipment_ref.get(transaction=txn)
            if not equipment_snap.exists:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            equipment = _load(Equipment, equipment_snap.to_dict())
            if equipment.status is not EquipmentStatus.AVAILABLE:
                raise BookingError(409, "unavailable", "This item is not operational.")
            for ref in lock_refs:
                if ref.get(transaction=txn).exists:
                    raise BookingError(409, "conflict", "This slot overlaps an existing booking.")
            for key, ref in zip(keys, lock_refs, strict=True):
                txn.set(
                    ref,
                    {
                        "equipment_id": equipment_id,
                        "offer_id": offer_id,
                        "slot_key": key,
                        "status": "offered",
                    },
                )

        run(transaction)

    def release_hold(self, *, equipment_id: str, start: datetime, end: datetime, offer_id: str) -> None:
        keys = slot_keys(equipment_id, start, end)
        transaction = self._client.transaction()
        lock_refs = [self._locks.document(key) for key in keys]

        @firestore.transactional
        def run(txn: firestore.Transaction) -> None:
            for ref in lock_refs:
                snap = ref.get(transaction=txn)
                data = snap.to_dict() if snap.exists else None
                if data and data.get("offer_id") == offer_id:
                    txn.delete(ref)

        run(transaction)

    def convert_hold(
        self,
        *,
        catalog: Catalog,
        offer_id: str,
        equipment_id: str,
        project_id: str,
        start: datetime,
        end: datetime,
        now: datetime,
        user_id: str,
        prerequisites_verified: bool = False,
    ) -> Booking:
        _require_future_range(start, end, now=now)
        lookup_project(catalog, project_id)
        equipment = lookup_equipment(catalog, equipment_id)
        if equipment.status is not EquipmentStatus.AVAILABLE:
            raise BookingError(409, "unavailable", "This item is not operational.")
        if equipment.safety_prerequisites and not prerequisites_verified:
            raise BookingError(403, "restricted", RESTRICTED_MESSAGE)
        keys = slot_keys(equipment.id, start, end)
        last_error: Exception | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                return self._convert_in_transaction(
                    offer_id=offer_id,
                    equipment_id=equipment.id,
                    project_id=project_id,
                    start=start,
                    end=end,
                    user_id=user_id,
                    keys=keys,
                )
            except _RETRYABLE as exc:
                last_error = exc
                continue
        raise BookingError(503, "request_failed", "The booking could not be completed.") from last_error

    def _convert_in_transaction(
        self,
        *,
        offer_id: str,
        equipment_id: str,
        project_id: str,
        start: datetime,
        end: datetime,
        user_id: str,
        keys: tuple[str, ...],
    ) -> Booking:
        transaction = self._client.transaction()
        booking_id = f"book-{uuid4().hex}"
        booking_ref = self._bookings.document(booking_id)
        equipment_ref = self._equipment.document(equipment_id)
        lock_refs = [self._locks.document(key) for key in keys]

        @firestore.transactional
        def run(txn: firestore.Transaction) -> Booking:
            equipment_snap = equipment_ref.get(transaction=txn)
            if not equipment_snap.exists:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            equipment = _load(Equipment, equipment_snap.to_dict())
            if equipment.status is not EquipmentStatus.AVAILABLE:
                raise BookingError(409, "unavailable", "This item is not operational.")
            for ref in lock_refs:
                lock_snap = ref.get(transaction=txn)
                data = lock_snap.to_dict() if lock_snap.exists else None
                if not data or data.get("offer_id") != offer_id:
                    raise BookingError(409, "conflict", "The offer hold is no longer valid.")
            booking = Booking(
                id=booking_id,
                user_id=user_id,
                equipment_id=equipment_id,
                project_id=project_id,
                start=start,
                end=end,
                status=BookingStatus.APPROVED,
            )
            txn.set(booking_ref, _dump(booking))
            for key, ref in zip(keys, lock_refs, strict=True):
                txn.set(
                    ref,
                    {
                        "equipment_id": equipment_id,
                        "booking_id": booking_id,
                        "slot_key": key,
                        "status": "held",
                    },
                )
            return booking

        return run(transaction)


class FirestoreAccessStore(AccessStore):
    def __init__(self, client: firestore.Client, bookings: FirestoreBookingStore) -> None:
        self._client = client
        self._requests = client.collection("access_requests")
        self._approvals = client.collection("approvals")
        self._decisions = client.collection("allocation_decisions")
        self._bookings = bookings

    def snapshot(self) -> list[AccessRequest]:
        return [_load(AccessRequest, snap.to_dict()) for snap in self._requests.stream()]

    def approvals_for(self, request_id: str) -> list[Approval]:
        query = self._approvals.where("request_id", "==", request_id)
        return [_load(Approval, snap.to_dict()) for snap in query.stream()]

    def approvals_snapshot(self) -> list[Approval]:
        return [_load(Approval, snap.to_dict()) for snap in self._approvals.stream()]

    def decisions_snapshot(self) -> list[AllocationDecision]:
        return [_load(AllocationDecision, snap.to_dict()) for snap in self._decisions.stream()]

    def submit(
        self,
        *,
        catalog: Catalog,
        actor: User,
        equipment_id: str,
        project_id: str,
        justification: str,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> AccessRequest:
        if actor.role is not Role.STUDENT:
            raise BookingError(403, "forbidden", "Only a student identity can submit requests.")
        lookup_equipment(catalog, equipment_id)
        lookup_project(catalog, project_id)
        if end <= start:
            raise BookingError(422, "invalid_request", "The request end must be after the start.")
        if start < now:
            raise BookingError(422, "invalid_request", "Access requests cannot start in the past.")
        for existing in self.snapshot():
            if (
                existing.user_id == actor.id
                and existing.equipment_id == equipment_id
                and existing.project_id == project_id
                and existing.status is RequestStatus.PENDING
                and existing.start == start
                and existing.end == end
            ):
                raise BookingError(409, "conflict", "An equivalent pending request already exists.")
        item = AccessRequest(
            id=f"req-{uuid4().hex}",
            user_id=actor.id,
            project_id=project_id,
            equipment_id=equipment_id,
            justification=justification,
            status=RequestStatus.PENDING,
            created_at=now,
            start=start,
            end=end,
        )
        self._requests.document(item.id).set(_dump(item))
        return item

    def decide(
        self,
        *,
        catalog: Catalog,
        bookings: BookingStore,
        actor: User,
        request_id: str,
        decision: ApprovalDecision,
        comments: str,
        now: datetime,
    ) -> tuple[AccessRequest, Approval, str | None]:
        if actor.role not in {Role.FACULTY, Role.ADMIN}:
            raise BookingError(403, "forbidden", "Only a faculty or admin identity can decide requests.")
        last_error: Exception | None = None
        competing: list[str] = []
        preview = self._requests.document(request_id).get()
        if preview.exists:
            previewed = _load(AccessRequest, preview.to_dict())
            competing = [
                item.id
                for item in self.snapshot()
                if item.id != request_id
                and item.equipment_id == previewed.equipment_id
                and item.status is RequestStatus.PENDING
            ]
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                return self._decide_in_transaction(
                    catalog=catalog,
                    actor=actor,
                    request_id=request_id,
                    decision=decision,
                    comments=comments,
                    now=now,
                    competing=competing,
                )
            except _RETRYABLE as exc:
                last_error = exc
                continue
        raise BookingError(503, "request_failed", "The decision could not be completed.") from last_error

    def _decide_in_transaction(
        self,
        *,
        catalog: Catalog,
        actor: User,
        request_id: str,
        decision: ApprovalDecision,
        comments: str,
        now: datetime,
        competing: list[str],
    ) -> tuple[AccessRequest, Approval, str | None]:
        """One transaction: request claim, approval audit, optional slot-locked booking.

        Slot-lock reads still happen before any writes. A slot conflict aborts the
        whole decision so the request stays pending. Faculty approval records
        `decided_at`; it does not skip range, equipment, or lock checks.
        """

        store = self._bookings
        request_ref = self._requests.document(request_id)
        approval_id = f"appr-{uuid4().hex}"
        approval_ref = self._approvals.document(approval_id)
        alloc_id = f"alloc-{uuid4().hex}"
        alloc_ref = self._decisions.document(alloc_id)
        booking_id = f"book-{uuid4().hex}"
        booking_ref = store._bookings.document(booking_id)
        transaction = self._client.transaction()

        @firestore.transactional
        def run(txn: firestore.Transaction) -> tuple[AccessRequest, Approval, str | None]:
            snap = request_ref.get(transaction=txn)
            if not snap.exists:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            current = _load(AccessRequest, snap.to_dict())
            if current.user_id == actor.id:
                raise BookingError(403, "forbidden", "A requester cannot approve their own request.")
            if current.status is not RequestStatus.PENDING:
                raise BookingError(409, "conflict", "This request is no longer pending.")
            equipment = lookup_equipment(catalog, current.equipment_id)
            require_faculty_scope(actor, equipment.department_id)
            lookup_project(catalog, current.project_id)

            created_booking: Booking | None = None
            lock_refs: list = []
            keys: tuple[str, ...] = ()
            if decision is ApprovalDecision.APPROVED and current.start is not None and current.end is not None:
                _require_future_range(current.start, current.end, now=now)
                equipment_ref = store._equipment.document(equipment.id)
                equipment_snap = equipment_ref.get(transaction=txn)
                if not equipment_snap.exists:
                    raise BookingError(404, "not_found", "The requested resource does not exist.")
                live = _load(Equipment, equipment_snap.to_dict())
                if live.status is not EquipmentStatus.AVAILABLE:
                    raise BookingError(409, "unavailable", "This item is not operational.")
                keys = slot_keys(equipment.id, current.start, current.end)
                lock_refs = [store._locks.document(key) for key in keys]
                for ref in lock_refs:
                    if ref.get(transaction=txn).exists:
                        raise BookingError(409, "conflict", "This slot overlaps an existing booking.")
                created_booking = Booking(
                    id=booking_id,
                    user_id=current.user_id,
                    equipment_id=equipment.id,
                    project_id=current.project_id,
                    start=current.start,
                    end=current.end,
                    status=BookingStatus.APPROVED,
                )

            status = RequestStatus.APPROVED if decision is ApprovalDecision.APPROVED else RequestStatus.REJECTED
            updated = current.model_copy(update={"status": status})
            approval = Approval(
                id=approval_id,
                request_id=current.id,
                faculty_id=actor.id,
                decision=decision,
                comments=comments,
                decided_at=now,
            )
            txn.set(request_ref, _dump(updated))
            txn.set(approval_ref, _dump(approval))
            if created_booking is not None:
                txn.set(booking_ref, _dump(created_booking))
                for key, ref in zip(keys, lock_refs, strict=True):
                    txn.set(
                        ref,
                        {
                            "equipment_id": created_booking.equipment_id,
                            "booking_id": created_booking.id,
                            "slot_key": key,
                            "status": "held",
                        },
                    )
            if decision is ApprovalDecision.APPROVED:
                alloc = AllocationDecision(
                    id=alloc_id,
                    equipment_id=current.equipment_id,
                    chosen_request_id=current.id,
                    faculty_id=actor.id,
                    explanation=comments,
                    competing_request_ids=competing,
                    created_at=now,
                )
                txn.set(alloc_ref, _dump(alloc))
            return updated, approval, created_booking.id if created_booking else None

        return run(transaction)

    def record_allocation(self, decision: AllocationDecision) -> None:
        self._decisions.document(decision.id).set(_dump(decision))


class FirestoreWaitlistStore(WaitlistStore):
    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._items = client.collection("waitlist")
        self._offers = client.collection("offers")

    def snapshot(self) -> list[WaitlistEntry]:
        return [_load(WaitlistEntry, snap.to_dict()) for snap in self._items.stream()]

    def offers_snapshot(self) -> list[SlotOffer]:
        return [_load(SlotOffer, snap.to_dict()) for snap in self._offers.stream()]

    def for_user(self, user_id: str) -> list[WaitlistEntry]:
        query = self._items.where("user_id", "==", user_id)
        return [_load(WaitlistEntry, snap.to_dict()) for snap in query.stream()]

    def get(self, entry_id: str) -> WaitlistEntry | None:
        snap = self._items.document(entry_id).get()
        if not snap.exists:
            return None
        return _load(WaitlistEntry, snap.to_dict())

    def join(self, entry: WaitlistEntry) -> WaitlistEntry:
        for existing in self.snapshot():
            if (
                existing.user_id == entry.user_id
                and existing.equipment_id == entry.equipment_id
                and existing.project_id == entry.project_id
                and existing.status in {WaitlistStatus.WAITING, WaitlistStatus.OFFERED}
            ):
                raise BookingError(409, "conflict", "An active waitlist entry already exists.")
        self._items.document(entry.id).set(_dump(entry))
        return entry

    def update(self, updated: WaitlistEntry) -> WaitlistEntry:
        snap = self._items.document(updated.id).get()
        if not snap.exists:
            raise BookingError(404, "not_found", "The requested resource does not exist.")
        self._items.document(updated.id).set(_dump(updated))
        return updated

    def put_offer(self, offer: SlotOffer) -> SlotOffer:
        self._offers.document(offer.id).set(_dump(offer))
        return offer

    def offer_by_id(self, offer_id: str) -> SlotOffer | None:
        snap = self._offers.document(offer_id).get()
        if not snap.exists:
            return None
        return _load(SlotOffer, snap.to_dict())

    def active_offer_for_equipment(self, equipment_id: str, *, now: datetime) -> SlotOffer | None:
        for item in self.offers_snapshot():
            if item.equipment_id == equipment_id and item.status is OfferStatus.OFFERED and item.expires_at > now:
                return item
        return None


def load_catalog(client: firestore.Client) -> Catalog:
    def collect(name: str, model: type[_T]) -> list[_T]:
        return [_load(model, snap.to_dict()) for snap in client.collection(name).stream()]

    from app.models import AccessRequest as AccessRequestModel
    from app.models import AllocationDecision as AllocationModel
    from app.models import Approval as ApprovalModel

    return Catalog(
        synthetic=True,
        departments=collect("departments", Department),
        labs=collect("labs", Lab),
        users=collect("users", User),
        equipment=collect("equipment", Equipment),
        projects=collect("projects", Project),
        bookings=collect("bookings", Booking),
        access_requests=collect("access_requests", AccessRequestModel),
        approvals=collect("approvals", ApprovalModel),
        allocation_decisions=collect("allocation_decisions", AllocationModel),
    )
