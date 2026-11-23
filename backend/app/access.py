"""Access requests and faculty decisions. Persistence is injected via stores."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from uuid import uuid4

from app.authn import require_faculty_scope
from app.bookings import BookingError, BookingStore, lookup_equipment, lookup_project
from app.models import (
    AccessRequest,
    AllocationDecision,
    Approval,
    ApprovalDecision,
    RequestStatus,
    Role,
    User,
)
from app.seed import Catalog

PENDING = RequestStatus.PENDING


class AccessStore:
    def __init__(
        self,
        requests: list[AccessRequest],
        approvals: list[Approval],
        decisions: list[AllocationDecision] | None = None,
    ) -> None:
        self._lock = Lock()
        self._requests = list(requests)
        self._approvals = list(approvals)
        self._decisions = list(decisions or [])

    def snapshot(self) -> list[AccessRequest]:
        with self._lock:
            return list(self._requests)

    def approvals_for(self, request_id: str) -> list[Approval]:
        with self._lock:
            return [item for item in self._approvals if item.request_id == request_id]

    def approvals_snapshot(self) -> list[Approval]:
        with self._lock:
            return list(self._approvals)

    def decisions_snapshot(self) -> list[AllocationDecision]:
        with self._lock:
            return list(self._decisions)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex}"

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
        equipment = lookup_equipment(catalog, equipment_id)
        project = lookup_project(catalog, project_id)
        if end <= start:
            raise BookingError(422, "invalid_request", "The request end must be after the start.")
        if start < now:
            raise BookingError(422, "invalid_request", "Access requests cannot start in the past.")
        with self._lock:
            for existing in self._requests:
                if (
                    existing.user_id == actor.id
                    and existing.equipment_id == equipment_id
                    and existing.project_id == project_id
                    and existing.status is PENDING
                    and existing.start == start
                    and existing.end == end
                ):
                    raise BookingError(409, "conflict", "An equivalent pending request already exists.")
            item = AccessRequest(
                id=self._next_id("req-live"),
                user_id=actor.id,
                project_id=project.id,
                equipment_id=equipment.id,
                justification=justification,
                status=PENDING,
                created_at=now,
                start=start,
                end=end,
            )
            self._requests.append(item)
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
        with self._lock:
            current = next((item for item in self._requests if item.id == request_id), None)
            if current is None:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            if current.user_id == actor.id:
                raise BookingError(403, "forbidden", "A requester cannot approve their own request.")
            if current.status is not PENDING:
                raise BookingError(409, "conflict", "This request is no longer pending.")
            equipment = lookup_equipment(catalog, current.equipment_id)
            require_faculty_scope(actor, equipment.department_id)
            booking_id: str | None = None
            competing = [
                item.id
                for item in self._requests
                if item.id != current.id
                and item.equipment_id == current.equipment_id
                and item.status is PENDING
            ]
            if decision is ApprovalDecision.APPROVED and current.start is not None and current.end is not None:
                booking = bookings.create(
                    catalog=catalog,
                    equipment_id=current.equipment_id,
                    project_id=current.project_id,
                    start=current.start,
                    end=current.end,
                    now=now,
                    user_id=current.user_id,
                    prerequisites_verified=True,
                )
                booking_id = booking.id
            status = (
                RequestStatus.APPROVED
                if decision is ApprovalDecision.APPROVED
                else RequestStatus.REJECTED
            )
            updated = current.model_copy(update={"status": status})
            approval = Approval(
                id=self._next_id("appr"),
                request_id=current.id,
                faculty_id=actor.id,
                decision=decision,
                comments=comments,
                decided_at=now,
            )
            self._requests = [updated if item.id == current.id else item for item in self._requests]
            self._approvals.append(approval)
            if decision is ApprovalDecision.APPROVED:
                self._decisions.append(
                    AllocationDecision(
                        id=self._next_id("alloc"),
                        equipment_id=current.equipment_id,
                        chosen_request_id=current.id,
                        faculty_id=actor.id,
                        explanation=comments,
                        competing_request_ids=competing,
                        created_at=now,
                    )
                )
            return updated, approval, booking_id

    def record_allocation(self, decision: AllocationDecision) -> None:
        with self._lock:
            self._decisions.append(decision)


def listed_for(
    actor: User,
    requests: list[AccessRequest],
    *,
    equipment_departments: dict[str, str],
) -> list[AccessRequest]:
    if actor.role is Role.ADMIN:
        return list(requests)
    if actor.role is Role.FACULTY:
        return [
            item
            for item in requests
            if equipment_departments.get(item.equipment_id) == actor.department_id
        ]
    if actor.role is Role.STUDENT:
        return [item for item in requests if item.user_id == actor.id]
    return []
