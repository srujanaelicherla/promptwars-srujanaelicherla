"""Booking rules and the process-local store.

Overlap safety uses slot lock keys from app.slots. The memory store serializes
those keys with a threading.Lock. That is not a distributed transaction.
Firestore persistence uses the same keys inside a Firestore transaction.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from app.models import Booking, BookingStatus, Equipment, EquipmentStatus, Project, Role, User
from app.schemas import ErrorCode
from app.seed import Catalog
from app.slots import SLOT, slot_keys

ACTIVE_STATUSES = frozenset({BookingStatus.REQUESTED, BookingStatus.APPROVED})
MIN_DURATION = SLOT
MAX_DURATION = timedelta(hours=8)
MAX_AVAILABILITY_SPAN = timedelta(days=7)
RESTRICTED_MESSAGE = (
    "This item needs faculty approval before it can be booked. Send an access request with a short reason."
)


class BookingError(Exception):
    def __init__(self, status_code: int, error: ErrorCode, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def _require_future_range(start: datetime, end: datetime, *, now: datetime) -> None:
    if end <= start:
        raise BookingError(422, "invalid_request", "The booking end must be after the start.")
    if start < now:
        raise BookingError(422, "invalid_request", "Bookings cannot start in the past.")
    duration = end - start
    if duration < MIN_DURATION:
        raise BookingError(422, "invalid_request", "The booking is shorter than the minimum duration.")
    if duration > MAX_DURATION:
        raise BookingError(422, "invalid_request", "The booking exceeds the maximum duration.")


def availability_window(
    *,
    on_date: date | None,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    if on_date is not None:
        if start is not None or end is not None:
            raise BookingError(422, "invalid_request", "Use a date or a time range, not both.")
        window_start = datetime(on_date.year, on_date.month, on_date.day, tzinfo=timezone.utc)
        return window_start, window_start + timedelta(days=1)
    if start is None or end is None:
        raise BookingError(422, "invalid_request", "Provide a date or both start and end.")
    if start.tzinfo is None or end.tzinfo is None:
        raise BookingError(422, "invalid_request", "Start and end must include a timezone.")
    if end <= start:
        raise BookingError(422, "invalid_request", "The range end must be after the start.")
    if end - start > MAX_AVAILABILITY_SPAN:
        raise BookingError(422, "invalid_request", "The availability range is too long.")
    return start, end


def subtract_busy(
    window_start: datetime,
    window_end: datetime,
    busy: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Return gaps in [window_start, window_end) after subtracting busy intervals."""

    clipped: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        lo = max(start, window_start)
        hi = min(end, window_end)
        if lo < hi:
            clipped.append((lo, hi))
    clipped.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end in clipped:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    gaps: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for start, end in merged:
        if cursor < start:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append((cursor, window_end))
    return gaps


class BookingStore:
    """Mutable booking list guarded by slot-lock keys and a process-local lock."""

    def __init__(self, initial: list[Booking]) -> None:
        self._lock = Lock()
        self._items = list(initial)
        self._locks: dict[str, str] = {}
        for item in initial:
            if item.status in ACTIVE_STATUSES:
                for key in slot_keys(item.equipment_id, item.start, item.end):
                    self._locks[key] = item.id

    def snapshot(self) -> list[Booking]:
        with self._lock:
            return list(self._items)

    def for_user(self, user_id: str) -> list[Booking]:
        with self._lock:
            return [item for item in self._items if item.user_id == user_id]

    def _next_id(self) -> str:
        return f"book-{uuid4().hex}"

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
        project = lookup_project(catalog, resolve_project_id(catalog, equipment, project_id))
        if equipment.status is not EquipmentStatus.AVAILABLE:
            raise BookingError(409, "unavailable", "This item is not operational.")
        if equipment.safety_prerequisites and not prerequisites_verified:
            raise BookingError(403, "restricted", RESTRICTED_MESSAGE)
        keys = slot_keys(equipment.id, start, end)
        with self._lock:
            live = lookup_equipment(catalog, equipment_id)
            if live.status is not EquipmentStatus.AVAILABLE:
                raise BookingError(409, "unavailable", "This item is not operational.")
            for key in keys:
                if key in self._locks:
                    raise BookingError(409, "conflict", "This slot overlaps an existing booking.")
            booking = Booking(
                id=self._next_id(),
                user_id=user_id,
                equipment_id=equipment.id,
                project_id=project.id,
                start=start,
                end=end,
                status=BookingStatus.APPROVED,
                purpose=purpose.strip()[:200],
            )
            for key in keys:
                self._locks[key] = booking.id
            self._items.append(booking)
            return booking

    def cancel(self, *, booking_id: str, actor: User) -> Booking:
        with self._lock:
            current = next((item for item in self._items if item.id == booking_id), None)
            if current is None:
                raise BookingError(404, "not_found", "The requested resource does not exist.")
            if current.user_id != actor.id and actor.role is not Role.ADMIN:
                raise BookingError(403, "forbidden", "This identity cannot cancel that booking.")
            if current.status not in ACTIVE_STATUSES:
                raise BookingError(409, "conflict", "This booking is not active.")
            for key in slot_keys(current.equipment_id, current.start, current.end):
                if self._locks.get(key) == current.id:
                    del self._locks[key]
            updated = current.model_copy(update={"status": BookingStatus.CANCELLED})
            self._items = [updated if item.id == current.id else item for item in self._items]
            return updated

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
        equipment = lookup_equipment(catalog, equipment_id)
        if equipment.status is not EquipmentStatus.AVAILABLE:
            raise BookingError(409, "unavailable", "This item is not operational.")
        keys = slot_keys(equipment.id, start, end)
        with self._lock:
            live = lookup_equipment(catalog, equipment_id)
            if live.status is not EquipmentStatus.AVAILABLE:
                raise BookingError(409, "unavailable", "This item is not operational.")
            for key in keys:
                if key in self._locks:
                    raise BookingError(409, "conflict", "This slot overlaps an existing booking.")
            for key in keys:
                self._locks[key] = offer_id

    def release_hold(self, *, equipment_id: str, start: datetime, end: datetime, offer_id: str) -> None:
        keys = slot_keys(equipment_id, start, end)
        with self._lock:
            for key in keys:
                if self._locks.get(key) == offer_id:
                    del self._locks[key]

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
        equipment = lookup_equipment(catalog, equipment_id)
        project = lookup_project(catalog, project_id)
        if equipment.status is not EquipmentStatus.AVAILABLE:
            raise BookingError(409, "unavailable", "This item is not operational.")
        if equipment.safety_prerequisites and not prerequisites_verified:
            raise BookingError(403, "restricted", RESTRICTED_MESSAGE)
        keys = slot_keys(equipment.id, start, end)
        with self._lock:
            for key in keys:
                if self._locks.get(key) != offer_id:
                    raise BookingError(409, "conflict", "The offer hold is no longer valid.")
            booking = Booking(
                id=self._next_id(),
                user_id=user_id,
                equipment_id=equipment.id,
                project_id=project.id,
                start=start,
                end=end,
                status=BookingStatus.APPROVED,
            )
            for key in keys:
                self._locks[key] = booking.id
            self._items.append(booking)
            return booking


def busy_intervals(bookings: list[Booking], equipment_id: str) -> list[tuple[datetime, datetime]]:
    return [
        (item.start, item.end)
        for item in bookings
        if item.equipment_id == equipment_id and item.status in ACTIVE_STATUSES
    ]


def lookup_equipment(catalog: Catalog, equipment_id: str) -> Equipment:
    for item in catalog.equipment:
        if item.id == equipment_id:
            return item
    raise BookingError(404, "not_found", "The requested resource does not exist.")


def lookup_project(catalog: Catalog, project_id: str) -> Project:
    for item in catalog.projects:
        if item.id == project_id:
            return item
    raise BookingError(404, "not_found", "The requested resource does not exist.")


def resolve_project_id(catalog: Catalog, equipment: Equipment, project_id: str | None) -> str:
    if project_id:
        return lookup_project(catalog, project_id).id
    for project in catalog.projects:
        if project.department_id == equipment.department_id:
            return project.id
    if catalog.projects:
        return catalog.projects[0].id
    raise BookingError(422, "invalid_request", "No project is available for this booking.")
