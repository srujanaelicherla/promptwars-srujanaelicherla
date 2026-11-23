"""Aggregates from stored bookings, equipment, requests, and waitlist.

Utilization percent is omitted when operating hours are unknown. Occupied
minutes are clipped to the requested window, cancelled bookings are excluded,
and overlapping confirmed intervals on one resource are merged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

from app.bookings import BookingError, overlaps
from app.models import (
    AccessRequest,
    Approval,
    ApprovalDecision,
    Booking,
    BookingStatus,
    Equipment,
    EquipmentStatus,
    RequestStatus,
    WaitlistEntry,
    WaitlistStatus,
)
from app.schemas import (
    AnalyticsCounts,
    AnalyticsOverview,
    ApprovalTurnaround,
    CategoryDemand,
    DepartmentAnalytics,
    DepartmentAnalyticsResponse,
    EquipmentAnalytics,
    EquipmentAnalyticsResponse,
    UtilizationView,
)
from app.seed import Catalog

_MAX_SPAN = timedelta(days=366)
_UNKNOWN_HOURS = (
    "Operating hours are not configured; eligible available resource-time cannot be computed."
)
CONFIRMED = BookingStatus.APPROVED


def parse_window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    if start is None or end is None:
        raise BookingError(422, "invalid_request", "Provide both start and end.")
    if start.tzinfo is None or end.tzinfo is None:
        raise BookingError(422, "invalid_request", "Start and end must include a timezone.")
    window_start = start.astimezone(timezone.utc)
    window_end = end.astimezone(timezone.utc)
    if window_end <= window_start:
        raise BookingError(422, "invalid_request", "The range end must be after the start.")
    if window_end - window_start > _MAX_SPAN:
        raise BookingError(422, "invalid_request", "The analytics range is too long.")
    return window_start, window_end


def _clip(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> tuple[datetime, datetime] | None:
    lo = max(start, window_start)
    hi = min(end, window_end)
    if lo >= hi:
        return None
    return lo, hi


def _merged_minutes(intervals: list[tuple[datetime, datetime]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    merged: list[tuple[datetime, datetime]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    total = sum((end - start).total_seconds() for start, end in merged)
    return int(total // 60)


def _utilization(occupied_minutes: int) -> UtilizationView:
    return UtilizationView(
        percent=None,
        occupied_minutes=occupied_minutes,
        available_minutes=None,
        unavailable_reason=_UNKNOWN_HOURS,
        capacity_per_slot=1,
    )


def _confirmed_in_window(
    bookings: list[Booking],
    window_start: datetime,
    window_end: datetime,
    equipment_ids: set[str] | None,
) -> list[Booking]:
    rows: list[Booking] = []
    for item in bookings:
        if item.status is not CONFIRMED:
            continue
        if equipment_ids is not None and item.equipment_id not in equipment_ids:
            continue
        if item.end <= window_start or item.start >= window_end:
            continue
        rows.append(item)
    return rows


def _occupied_for(
    bookings: list[Booking],
    equipment_id: str,
    window_start: datetime,
    window_end: datetime,
) -> int:
    clips: list[tuple[datetime, datetime]] = []
    for item in bookings:
        if item.equipment_id != equipment_id:
            continue
        clipped = _clip(item.start, item.end, window_start, window_end)
        if clipped:
            clips.append(clipped)
    return _merged_minutes(clips)


def _pending(requests: list[AccessRequest], equipment_ids: set[str]) -> list[AccessRequest]:
    return [
        item
        for item in requests
        if item.status is RequestStatus.PENDING and item.equipment_id in equipment_ids
    ]


def _waiting(entries: list[WaitlistEntry], equipment_ids: set[str]) -> list[WaitlistEntry]:
    return [
        item
        for item in entries
        if item.status is WaitlistStatus.WAITING and item.equipment_id in equipment_ids
    ]


def _conflicts(pending: list[AccessRequest]) -> int:
    count = 0
    by_equipment: dict[str, list[AccessRequest]] = {}
    for item in pending:
        by_equipment.setdefault(item.equipment_id, []).append(item)
    for group in by_equipment.values():
        competing = False
        for index, left in enumerate(group):
            if left.start is None or left.end is None:
                continue
            for right in group[index + 1 :]:
                if right.start is None or right.end is None:
                    continue
                if overlaps(left.start, left.end, right.start, right.end):
                    competing = True
                    break
            if competing:
                break
        if competing:
            count += 1
    return count


def _turnaround(requests: list[AccessRequest], approvals: list[Approval], equipment_ids: set[str]) -> ApprovalTurnaround:
    by_request = {item.request_id: item for item in approvals if item.decision is ApprovalDecision.APPROVED}
    hours: list[float] = []
    for item in requests:
        if item.equipment_id not in equipment_ids:
            continue
        approval = by_request.get(item.id)
        if approval is None:
            continue
        delta = (approval.decided_at - item.created_at).total_seconds() / 3600.0
        if delta >= 0:
            hours.append(delta)
    if not hours:
        return ApprovalTurnaround(
            sample_size=0,
            median_hours=None,
            unavailable_reason="No approval timestamps fall in the authorized equipment set.",
        )
    return ApprovalTurnaround(sample_size=len(hours), median_hours=round(median(hours), 2), unavailable_reason=None)


def _equipment_row(
    equipment: Equipment,
    confirmed: list[Booking],
    pending: list[AccessRequest],
    waiting: list[WaitlistEntry],
    window_start: datetime,
    window_end: datetime,
) -> EquipmentAnalytics:
    occupied = _occupied_for(confirmed, equipment.id, window_start, window_end)
    confirmed_count = sum(1 for item in confirmed if item.equipment_id == equipment.id)
    pending_count = sum(1 for item in pending if item.equipment_id == equipment.id)
    waiting_count = sum(1 for item in waiting if item.equipment_id == equipment.id)
    return EquipmentAnalytics(
        equipment_id=equipment.id,
        name=equipment.name,
        department_id=equipment.department_id,
        category=equipment.category,
        occupied_minutes=occupied,
        confirmed_bookings=confirmed_count,
        pending_requests=pending_count,
        waitlist_waiting=waiting_count,
        underused=occupied == 0 and equipment.status is EquipmentStatus.AVAILABLE,
        utilization=_utilization(occupied),
    )


def scoped_equipment(catalog: Catalog, department_id: str | None) -> list[Equipment]:
    if department_id is None:
        return list(catalog.equipment)
    return [item for item in catalog.equipment if item.department_id == department_id]


def build_overview(
    *,
    catalog: Catalog,
    bookings: list[Booking],
    requests: list[AccessRequest],
    approvals: list[Approval],
    waitlist: list[WaitlistEntry],
    window_start: datetime,
    window_end: datetime,
    department_id: str | None,
) -> AnalyticsOverview:
    equipment = scoped_equipment(catalog, department_id)
    ids = {item.id for item in equipment}
    confirmed = _confirmed_in_window(bookings, window_start, window_end, ids)
    pending = _pending(requests, ids)
    waiting = _waiting(waitlist, ids)
    offered = [
        item
        for item in waitlist
        if item.status is WaitlistStatus.OFFERED and item.equipment_id in ids
    ]
    rows = [
        _equipment_row(item, confirmed, pending, waiting, window_start, window_end) for item in equipment
    ]
    occupied = sum(row.occupied_minutes for row in rows)
    most_booked = sorted(rows, key=lambda row: (-row.occupied_minutes, -row.confirmed_bookings, row.equipment_id))
    wait_demand = sorted(
        [row for row in rows if row.waitlist_waiting > 0],
        key=lambda row: (-row.waitlist_waiting, row.equipment_id),
    )
    categories: dict[str, CategoryDemand] = {}
    for row in rows:
        current = categories.get(row.category)
        if current is None:
            categories[row.category] = CategoryDemand(
                category=row.category,
                pending_requests=row.pending_requests,
                waitlist_waiting=row.waitlist_waiting,
                confirmed_bookings=row.confirmed_bookings,
            )
        else:
            categories[row.category] = CategoryDemand(
                category=row.category,
                pending_requests=current.pending_requests + row.pending_requests,
                waitlist_waiting=current.waitlist_waiting + row.waitlist_waiting,
                confirmed_bookings=current.confirmed_bookings + row.confirmed_bookings,
            )
    demand = sorted(categories.values(), key=lambda item: (-item.pending_requests, item.category))
    active = sum(1 for item in equipment if item.status is EquipmentStatus.AVAILABLE)
    return AnalyticsOverview(
        start=window_start,
        end=window_end,
        counts=AnalyticsCounts(
            equipment_total=len(equipment),
            equipment_active=active,
            confirmed_bookings=len(confirmed),
            pending_requests=len(pending),
            waitlist_waiting=len(waiting),
            waitlist_offered=len(offered),
            conflicts=_conflicts(pending),
        ),
        utilization=_utilization(occupied),
        most_booked=most_booked[:8],
        demand_by_category=demand,
        waitlist_demand=wait_demand[:8],
        approval_turnaround=_turnaround(requests, approvals, ids),
        source="synthetic",
        demo=True,
    )


def build_departments(
    *,
    catalog: Catalog,
    bookings: list[Booking],
    requests: list[AccessRequest],
    waitlist: list[WaitlistEntry],
    window_start: datetime,
    window_end: datetime,
    department_id: str | None,
) -> DepartmentAnalyticsResponse:
    equipment = scoped_equipment(catalog, department_id)
    ids = {item.id for item in equipment}
    confirmed = _confirmed_in_window(bookings, window_start, window_end, ids)
    pending = _pending(requests, ids)
    waiting = _waiting(waitlist, ids)
    departments = catalog.departments if department_id is None else [item for item in catalog.departments if item.id == department_id]
    items: list[DepartmentAnalytics] = []
    for dept in departments:
        eq_ids = {item.id for item in equipment if item.department_id == dept.id}
        occupied = sum(_occupied_for(confirmed, eq_id, window_start, window_end) for eq_id in eq_ids)
        items.append(
            DepartmentAnalytics(
                department_id=dept.id,
                occupied_minutes=occupied,
                confirmed_bookings=sum(1 for item in confirmed if item.equipment_id in eq_ids),
                pending_requests=sum(1 for item in pending if item.equipment_id in eq_ids),
                waitlist_waiting=sum(1 for item in waiting if item.equipment_id in eq_ids),
                utilization=_utilization(occupied),
            )
        )
    items.sort(key=lambda row: row.department_id)
    return DepartmentAnalyticsResponse(
        start=window_start,
        end=window_end,
        items=items,
        source="synthetic",
        demo=True,
    )


def build_equipment(
    *,
    catalog: Catalog,
    bookings: list[Booking],
    requests: list[AccessRequest],
    waitlist: list[WaitlistEntry],
    window_start: datetime,
    window_end: datetime,
    department_id: str | None,
) -> EquipmentAnalyticsResponse:
    equipment = scoped_equipment(catalog, department_id)
    ids = {item.id for item in equipment}
    confirmed = _confirmed_in_window(bookings, window_start, window_end, ids)
    pending = _pending(requests, ids)
    waiting = _waiting(waitlist, ids)
    rows = [
        _equipment_row(item, confirmed, pending, waiting, window_start, window_end) for item in equipment
    ]
    rows.sort(key=lambda row: row.equipment_id)
    return EquipmentAnalyticsResponse(
        start=window_start,
        end=window_end,
        items=rows,
        source="synthetic",
        demo=True,
    )
