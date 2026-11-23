"""Deterministic slot search. Advisory only; bookings revalidate on create."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.bookings import (
    MAX_AVAILABILITY_SPAN,
    MAX_DURATION,
    MIN_DURATION,
    BookingError,
    busy_intervals,
    lookup_equipment,
    lookup_project,
    overlaps,
)
from app.matching import rank_matches, score_equipment
from app.models import Booking, Equipment, EquipmentStatus, SlotOffer, OfferStatus
from app.schemas import AlternativeEquipment, RecommendedSlot, SchedulingResponse
from app.seed import Catalog
from app.slots import SLOT, floor_slot

_UNKNOWN = (
    "Operating hours are not configured; they were not applied.",
    "Maintenance windows are not configured; they were not applied.",
)
_MAX_RETURN = 8
_MAX_STEPS = 672
_ALLOWED_INCREMENTS = {15, 30, 60}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise BookingError(422, "invalid_request", "Start and end must include a timezone.")
    return value.astimezone(timezone.utc)


def _duration(minutes: int) -> timedelta:
    if minutes % 15 != 0:
        raise BookingError(422, "invalid_request", "Duration must be a multiple of 15 minutes.")
    span = timedelta(minutes=minutes)
    if span < MIN_DURATION or span > MAX_DURATION:
        raise BookingError(422, "invalid_request", "Duration is outside the allowed range.")
    return span


def search_window(
    *,
    preferred_start: datetime,
    preferred_end: datetime,
    flexibility_minutes: int,
    now: datetime,
) -> tuple[datetime, datetime, list[str]]:
    start = _utc(preferred_start)
    end = _utc(preferred_end)
    notes: list[str] = []
    if end <= start:
        raise BookingError(422, "invalid_request", "The preferred end must be after the start.")
    flex = timedelta(minutes=max(0, flexibility_minutes))
    window_start = start - flex
    window_end = end + flex
    if window_end - window_start > MAX_AVAILABILITY_SPAN:
        window_end = window_start + MAX_AVAILABILITY_SPAN
        notes.append("The search window was clamped to seven days.")
    if window_end <= now:
        raise BookingError(422, "invalid_request", "The preferred range is in the past.")
    if window_start < now:
        window_start = now
    return window_start, window_end, notes


def combined_busy(
    bookings: list[Booking],
    offers: list[SlotOffer],
    equipment_id: str,
    *,
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    busy = busy_intervals(bookings, equipment_id)
    for offer in offers:
        if offer.equipment_id != equipment_id:
            continue
        if offer.status is not OfferStatus.OFFERED:
            continue
        if offer.expires_at <= now:
            continue
        busy.append((offer.start, offer.end))
    return busy


def _slot_fits(
    start: datetime,
    duration: timedelta,
    window_end: datetime,
    busy: list[tuple[datetime, datetime]],
) -> bool:
    finish = start + duration
    if finish > window_end:
        return False
    return all(not overlaps(start, finish, lo, hi) for lo, hi in busy)


def iter_starts(window_start: datetime, window_end: datetime, increment: timedelta) -> list[datetime]:
    cursor = floor_slot(window_start)
    if cursor < window_start:
        cursor += SLOT
    while cursor.minute % int(increment.total_seconds() // 60) != 0:
        cursor += SLOT
        if cursor >= window_end:
            return []
    starts: list[datetime] = []
    steps = 0
    while cursor < window_end and steps < _MAX_STEPS:
        starts.append(cursor)
        cursor += increment
        steps += 1
    return starts


def _base_constraints(equipment: Equipment, extra: list[str]) -> list[str]:
    notes = list(_UNKNOWN)
    notes.extend(extra)
    if equipment.status is EquipmentStatus.MAINTENANCE:
        notes.append("Equipment is recorded as maintenance; live repair windows are unknown.")
    if equipment.status is EquipmentStatus.RETIRED:
        notes.append("Equipment is recorded as retired.")
    return notes


def recommend_for_equipment(
    *,
    equipment: Equipment,
    project_requirements,
    window_start: datetime,
    window_end: datetime,
    duration: timedelta,
    increment: timedelta,
    preferred_start: datetime,
    busy: list[tuple[datetime, datetime]],
    extra_constraints: list[str],
) -> list[RecommendedSlot]:
    if equipment.status is not EquipmentStatus.AVAILABLE:
        return []
    match = score_equipment(equipment, project_requirements)
    constraints = _base_constraints(equipment, extra_constraints)
    starts = iter_starts(window_start, window_end, increment)
    ranked: list[tuple[timedelta, datetime, RecommendedSlot]] = []
    preferred = _utc(preferred_start)
    for start in starts:
        if not _slot_fits(start, duration, window_end, busy):
            continue
        finish = start + duration
        delta = start - preferred if start >= preferred else preferred - start
        explanation = (
            f"{equipment.name} is free {start.isoformat()}–{finish.isoformat()} UTC. "
            f"{match.explanation} This recommendation is advisory and is not a hold."
        )
        ranked.append(
            (
                delta,
                start,
                RecommendedSlot(
                    equipment_id=equipment.id,
                    start=start,
                    end=finish,
                    suitability=match.suitability,
                    explanation=explanation[:500],
                    constraints=constraints,
                    advisory=True,
                ),
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1], item[2].equipment_id))
    return [item[2] for item in ranked[:_MAX_RETURN]]


def recommend(
    *,
    catalog: Catalog,
    bookings: list[Booking],
    offers: list[SlotOffer],
    equipment_id: str,
    project_id: str,
    duration_minutes: int,
    preferred_start: datetime,
    preferred_end: datetime,
    flexibility_minutes: int,
    increment_minutes: int,
    now: datetime,
) -> SchedulingResponse:
    if increment_minutes not in _ALLOWED_INCREMENTS:
        raise BookingError(422, "invalid_request", "Increment must be 15, 30, or 60 minutes.")
    duration = _duration(duration_minutes)
    increment = timedelta(minutes=increment_minutes)
    equipment = lookup_equipment(catalog, equipment_id)
    project = lookup_project(catalog, project_id)
    window_start, window_end, clamp_notes = search_window(
        preferred_start=preferred_start,
        preferred_end=preferred_end,
        flexibility_minutes=flexibility_minutes,
        now=now,
    )
    busy = combined_busy(bookings, offers, equipment.id, now=now)
    extra = list(clamp_notes)
    slots = recommend_for_equipment(
        equipment=equipment,
        project_requirements=project.required_specifications,
        window_start=window_start,
        window_end=window_end,
        duration=duration,
        increment=increment,
        preferred_start=preferred_start,
        busy=busy,
        extra_constraints=extra,
    )
    alternatives: list[AlternativeEquipment] = []
    if not slots or equipment.status is not EquipmentStatus.AVAILABLE:
        ranked = rank_matches(catalog.equipment, project.required_specifications)
        for row in ranked:
            if row.equipment.id == equipment.id:
                continue
            if not row.mandatory_ok:
                continue
            if row.equipment.status is not EquipmentStatus.AVAILABLE:
                continue
            alt_busy = combined_busy(bookings, offers, row.equipment.id, now=now)
            alt_slots = recommend_for_equipment(
                equipment=row.equipment,
                project_requirements=project.required_specifications,
                window_start=window_start,
                window_end=window_end,
                duration=duration,
                increment=increment,
                preferred_start=preferred_start,
                busy=alt_busy,
                extra_constraints=extra,
            )
            if not alt_slots:
                continue
            alternatives.append(
                AlternativeEquipment(
                    equipment_id=row.equipment.id,
                    name=row.equipment.name,
                    suitability=row.suitability,
                    mandatory_ok=True,
                    explanation=row.explanation,
                    slots=alt_slots[:3],
                )
            )
            if len(alternatives) >= 3:
                break
    constraints = _base_constraints(equipment, extra)
    return SchedulingResponse(
        equipment_id=equipment.id,
        slots=slots,
        alternatives=alternatives,
        constraints=constraints,
        waitlist_eligible=len(slots) == 0,
        source="synthetic",
        demo=True,
    )
