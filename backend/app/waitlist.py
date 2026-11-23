"""Persistent waitlist, time-limited offers, and advisory promotion.

Promotion is an authenticated, idempotent operation. It is not a deployed job.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from uuid import uuid4

from app.access import AccessStore
from app.bookings import BookingError, BookingStore, lookup_equipment, lookup_project
from app.conflicts import evaluate_conflicts
from app.models import (
    AccessRequest,
    AllocationDecision,
    EquipmentStatus,
    OfferStatus,
    RequestStatus,
    Role,
    SlotOffer,
    User,
    WaitlistEntry,
    WaitlistStatus,
)
from app.scheduling import recommend
from app.seed import Catalog

OFFER_TTL = timedelta(minutes=30)
ACTIVE = frozenset({WaitlistStatus.WAITING, WaitlistStatus.OFFERED})


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class WaitlistStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: list[WaitlistEntry] = []
        self._offers: list[SlotOffer] = []

    def snapshot(self) -> list[WaitlistEntry]:
        with self._lock:
            return list(self._items)

    def offers_snapshot(self) -> list[SlotOffer]:
        with self._lock:
            return list(self._offers)

    def for_user(self, user_id: str) -> list[WaitlistEntry]:
        with self._lock:
            return [item for item in self._items if item.user_id == user_id]

    def get(self, entry_id: str) -> WaitlistEntry | None:
        with self._lock:
            return next((item for item in self._items if item.id == entry_id), None)

    def join(self, entry: WaitlistEntry) -> WaitlistEntry:
        with self._lock:
            for existing in self._items:
                if (
                    existing.user_id == entry.user_id
                    and existing.equipment_id == entry.equipment_id
                    and existing.project_id == entry.project_id
                    and existing.status in ACTIVE
                ):
                    raise BookingError(409, "conflict", "An active waitlist entry already exists.")
            self._items.append(entry)
            return entry

    def update(self, updated: WaitlistEntry) -> WaitlistEntry:
        with self._lock:
            found = False
            next_items: list[WaitlistEntry] = []
            for item in self._items:
                if item.id == updated.id:
                    next_items.append(updated)
                    found = True
                else:
                    next_items.append(item)
            if not found:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            self._items = next_items
            return updated

    def put_offer(self, offer: SlotOffer) -> SlotOffer:
        with self._lock:
            self._offers = [item for item in self._offers if item.id != offer.id]
            self._offers.append(offer)
            return offer

    def offer_by_id(self, offer_id: str) -> SlotOffer | None:
        with self._lock:
            return next((item for item in self._offers if item.id == offer_id), None)

    def active_offer_for_equipment(self, equipment_id: str, *, now: datetime) -> SlotOffer | None:
        with self._lock:
            for item in self._offers:
                if (
                    item.equipment_id == equipment_id
                    and item.status is OfferStatus.OFFERED
                    and item.expires_at > now
                ):
                    return item
            return None


def waiting_as_requests(entries: list[WaitlistEntry]) -> list[AccessRequest]:
    mapped: list[AccessRequest] = []
    for item in entries:
        if item.status is not WaitlistStatus.WAITING:
            continue
        mapped.append(
            AccessRequest(
                id=item.id,
                user_id=item.user_id,
                project_id=item.project_id,
                equipment_id=item.equipment_id,
                justification="waitlist",
                status=RequestStatus.PENDING,
                created_at=item.created_at,
                start=item.preferred_start,
                end=item.preferred_end,
            )
        )
    return mapped


def rank_waitlist(
    *,
    catalog: Catalog,
    equipment_id: str,
    entries: list[WaitlistEntry],
    bookings,
    now: datetime,
    viewer_is_faculty: bool,
):
    equipment = lookup_equipment(catalog, equipment_id)
    return evaluate_conflicts(
        catalog=catalog,
        equipment=equipment,
        requests=waiting_as_requests(entries),
        bookings=bookings,
        now=now,
        viewer_is_faculty=viewer_is_faculty,
    )


def approval_holds(access: AccessStore, *, user_id: str, equipment_id: str) -> bool:
    for item in access.snapshot():
        if item.user_id == user_id and item.equipment_id == equipment_id and item.status is RequestStatus.APPROVED:
            return True
    return False


def expire_offers(*, waitlist: WaitlistStore, bookings: BookingStore, now: datetime) -> None:
    for offer in waitlist.offers_snapshot():
        if offer.status is not OfferStatus.OFFERED:
            continue
        if offer.expires_at > now:
            continue
        bookings.release_hold(
            equipment_id=offer.equipment_id,
            start=offer.start,
            end=offer.end,
            offer_id=offer.id,
        )
        waitlist.put_offer(offer.model_copy(update={"status": OfferStatus.EXPIRED}))
        entry = waitlist.get(offer.waitlist_id)
        if entry is not None and entry.status is WaitlistStatus.OFFERED:
            waitlist.update(
                entry.model_copy(
                    update={
                        "status": WaitlistStatus.EXPIRED,
                        "updated_at": now,
                    }
                )
            )


def promote(
    *,
    catalog: Catalog,
    bookings: BookingStore,
    waitlist: WaitlistStore,
    access: AccessStore,
    equipment_id: str,
    actor: User,
    now: datetime,
) -> tuple[SlotOffer | None, bool]:
    """Return (offer, already_existed). Not a background worker."""

    last_conflict: BookingError | None = None
    for _attempt in range(2):
        try:
            return _promote_once(
                catalog=catalog,
                bookings=bookings,
                waitlist=waitlist,
                access=access,
                equipment_id=equipment_id,
                actor=actor,
                now=now,
            )
        except BookingError as exc:
            if exc.status_code != 409:
                raise
            last_conflict = exc
            existing = waitlist.active_offer_for_equipment(equipment_id, now=now)
            if existing is not None:
                return existing, True
    if last_conflict is not None:
        existing = waitlist.active_offer_for_equipment(equipment_id, now=now)
        if existing is not None:
            return existing, True
        raise last_conflict
    return None, False


def _promote_once(
    *,
    catalog: Catalog,
    bookings: BookingStore,
    waitlist: WaitlistStore,
    access: AccessStore,
    equipment_id: str,
    actor: User,
    now: datetime,
) -> tuple[SlotOffer | None, bool]:
    expire_offers(waitlist=waitlist, bookings=bookings, now=now)
    existing = waitlist.active_offer_for_equipment(equipment_id, now=now)
    if existing is not None:
        return existing, True
    equipment = lookup_equipment(catalog, equipment_id)
    if equipment.status is not EquipmentStatus.AVAILABLE:
        return None, False
    entries = [item for item in waitlist.snapshot() if item.equipment_id == equipment_id]
    rows = rank_waitlist(
        catalog=catalog,
        equipment_id=equipment_id,
        entries=entries,
        bookings=bookings.snapshot(),
        now=now,
        viewer_is_faculty=True,
    )
    top = next((row for row in rows if row.eligible and row.feasible), None)
    if top is None:
        return None, False
    entry = waitlist.get(top.request_id)
    if entry is None or entry.status is not WaitlistStatus.WAITING:
        return None, False
    rec = recommend(
        catalog=catalog,
        bookings=bookings.snapshot(),
        offers=waitlist.offers_snapshot(),
        equipment_id=equipment_id,
        project_id=entry.project_id,
        duration_minutes=entry.duration_minutes,
        preferred_start=entry.preferred_start,
        preferred_end=entry.preferred_end,
        flexibility_minutes=entry.flexibility_minutes,
        increment_minutes=15,
        now=now,
    )
    if not rec.slots:
        return None, False
    slot = rec.slots[0]
    offer_id = _new_id("offer")
    bookings.acquire_hold(
        catalog=catalog,
        equipment_id=equipment_id,
        start=slot.start,
        end=slot.end,
        now=now,
        offer_id=offer_id,
    )
    offer = SlotOffer(
        id=offer_id,
        waitlist_id=entry.id,
        user_id=entry.user_id,
        equipment_id=equipment_id,
        project_id=entry.project_id,
        start=slot.start,
        end=slot.end,
        expires_at=now + OFFER_TTL,
        status=OfferStatus.OFFERED,
        created_at=now,
    )
    waitlist.put_offer(offer)
    waitlist.update(
        entry.model_copy(
            update={
                "status": WaitlistStatus.OFFERED,
                "updated_at": now,
                "offer_id": offer.id,
                "offered_start": offer.start,
                "offered_end": offer.end,
                "offer_expires_at": offer.expires_at,
            }
        )
    )
    competing = [row.request_id for row in rows if row.request_id != entry.id]
    access.record_allocation(
        AllocationDecision(
            id=_new_id("alloc"),
            equipment_id=equipment_id,
            chosen_request_id=entry.id,
            faculty_id=actor.id,
            explanation="Waitlist promotion created a time-limited offer hold. It is not a confirmed booking.",
            competing_request_ids=competing[:50],
            created_at=now,
        )
    )
    return offer, False


def join_waitlist(
    *,
    catalog: Catalog,
    bookings: BookingStore,
    waitlist: WaitlistStore,
    actor: User,
    equipment_id: str,
    project_id: str,
    duration_minutes: int,
    preferred_start: datetime,
    preferred_end: datetime,
    flexibility_minutes: int,
    now: datetime,
) -> WaitlistEntry:
    if actor.role is not Role.STUDENT:
        raise BookingError(403, "forbidden", "Only a student identity can join the waitlist.")
    lookup_equipment(catalog, equipment_id)
    lookup_project(catalog, project_id)
    rec = recommend(
        catalog=catalog,
        bookings=bookings.snapshot(),
        offers=waitlist.offers_snapshot(),
        equipment_id=equipment_id,
        project_id=project_id,
        duration_minutes=duration_minutes,
        preferred_start=preferred_start,
        preferred_end=preferred_end,
        flexibility_minutes=flexibility_minutes,
        increment_minutes=15,
        now=now,
    )
    if rec.slots:
        raise BookingError(409, "conflict", "A suitable slot is available. Recommendations are not a hold.")
    entry = WaitlistEntry(
        id=_new_id("wait"),
        user_id=actor.id,
        equipment_id=equipment_id,
        project_id=project_id,
        duration_minutes=duration_minutes,
        preferred_start=preferred_start,
        preferred_end=preferred_end,
        flexibility_minutes=flexibility_minutes,
        status=WaitlistStatus.WAITING,
        created_at=now,
        updated_at=now,
    )
    return waitlist.join(entry)


def cancel_entry(*, waitlist: WaitlistStore, bookings: BookingStore, actor: User, entry_id: str, now: datetime) -> WaitlistEntry:
    entry = waitlist.get(entry_id)
    if entry is None:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    if entry.user_id != actor.id and actor.role is not Role.ADMIN:
        raise BookingError(403, "forbidden", "This identity cannot cancel that waitlist entry.")
    if entry.status not in ACTIVE:
        raise BookingError(409, "conflict", "This waitlist entry is no longer active.")
    if entry.status is WaitlistStatus.OFFERED and entry.offer_id and entry.offered_start and entry.offered_end:
        bookings.release_hold(
            equipment_id=entry.equipment_id,
            start=entry.offered_start,
            end=entry.offered_end,
            offer_id=entry.offer_id,
        )
        offer = waitlist.offer_by_id(entry.offer_id)
        if offer is not None:
            waitlist.put_offer(offer.model_copy(update={"status": OfferStatus.RELEASED}))
    return waitlist.update(
        entry.model_copy(update={"status": WaitlistStatus.CANCELLED, "updated_at": now, "offer_id": None})
    )


def accept_offer(
    *,
    catalog: Catalog,
    bookings: BookingStore,
    waitlist: WaitlistStore,
    access: AccessStore,
    actor: User,
    entry_id: str,
    now: datetime,
):
    expire_offers(waitlist=waitlist, bookings=bookings, now=now)
    entry = waitlist.get(entry_id)
    if entry is None:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    if entry.user_id != actor.id:
        raise BookingError(403, "forbidden", "This identity cannot accept that offer.")
    if entry.status is not WaitlistStatus.OFFERED or entry.offer_id is None:
        raise BookingError(409, "conflict", "There is no active offer to accept.")
    offer = waitlist.offer_by_id(entry.offer_id)
    if offer is None or offer.status is not OfferStatus.OFFERED or offer.expires_at <= now:
        raise BookingError(409, "conflict", "The offer has expired.")
    equipment = lookup_equipment(catalog, entry.equipment_id)
    verified = not equipment.safety_prerequisites or approval_holds(
        access, user_id=actor.id, equipment_id=equipment.id
    )
    if equipment.safety_prerequisites and not verified:
        raise BookingError(
            403,
            "restricted",
            "Prerequisites are not verified. The offer was not converted to a booking.",
        )
    booking = bookings.convert_hold(
        catalog=catalog,
        offer_id=offer.id,
        equipment_id=offer.equipment_id,
        project_id=offer.project_id,
        start=offer.start,
        end=offer.end,
        now=now,
        user_id=actor.id,
        prerequisites_verified=verified,
    )
    waitlist.put_offer(offer.model_copy(update={"status": OfferStatus.ACCEPTED}))
    waitlist.update(entry.model_copy(update={"status": WaitlistStatus.FULFILLED, "updated_at": now}))
    return booking
