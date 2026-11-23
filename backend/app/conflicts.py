"""Deterministic conflict ranking for pending equipment requests.

Weights (configurable, not policy): deadline 0.30, suitability 0.25,
fair access 0.20, alternatives 0.15, waiting 0.10.

Each present input is min-max normalized within the competing set.
Missing inputs contribute 0 and mark the ranking provisional.
Hard eligibility/feasibility is applied before scoring. Ineligible
requests cannot outrank eligible ones. Tie-break is request id.

This uses catalog specs, request timestamps, project deadlines, and
booking counts. It does not invent usage history or live slots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.bookings import overlaps
from app.matching import rank_matches, score_equipment
from app.models import (
    AccessRequest,
    Booking,
    BookingStatus,
    Equipment,
    EquipmentStatus,
    Project,
    RequestStatus,
)
from app.seed import Catalog

WEIGHTS = {
    "deadline_urgency": 0.30,
    "suitability": 0.25,
    "fair_access": 0.20,
    "alternatives": 0.15,
    "waiting": 0.10,
}


@dataclass(frozen=True)
class ConflictRow:
    request_id: str
    project_id: str
    requester_department_id: str
    requester_user_id: str | None
    eligible: bool
    feasible: bool
    provisional: bool
    score: float | None
    rank: int | None
    components: dict[str, float | None]
    missing_inputs: tuple[str, ...]
    explanation: str
    alternatives: tuple[str, ...]


def _minmax(values: list[float | None]) -> list[float | None]:
    present = [item for item in values if item is not None]
    if not present:
        return list(values)
    lo, hi = min(present), max(present)
    if hi == lo:
        return [1.0 if item is not None else None for item in values]
    return [None if item is None else (item - lo) / (hi - lo) for item in values]


def evaluate_conflicts(
    *,
    catalog: Catalog,
    equipment: Equipment,
    requests: list[AccessRequest],
    bookings: list[Booking],
    now: datetime,
    viewer_is_faculty: bool,
) -> list[ConflictRow]:
    pending = [
        item
        for item in requests
        if item.equipment_id == equipment.id and item.status is RequestStatus.PENDING
    ]
    pending.sort(key=lambda item: item.id)
    users = {user.id: user for user in catalog.users}
    projects = {item.id: item for item in catalog.projects}

    raw: list[dict[str, float | None]] = []
    meta: list[tuple[AccessRequest, bool, bool, tuple[str, ...], tuple[str, ...]]] = []

    for item in pending:
        project = projects.get(item.project_id)
        user = users.get(item.user_id)
        missing: list[str] = []
        eligible = project is not None and user is not None
        feasible = equipment.status is EquipmentStatus.AVAILABLE
        if item.start is not None and item.end is not None:
            if item.end <= item.start or item.start < now:
                feasible = False
            for booking in bookings:
                if booking.equipment_id != equipment.id:
                    continue
                if booking.status not in {BookingStatus.REQUESTED, BookingStatus.APPROVED}:
                    continue
                if overlaps(item.start, item.end, booking.start, booking.end):
                    feasible = False
                    break
        else:
            missing.append("requested_slot")

        components: dict[str, float | None] = {key: None for key in WEIGHTS}
        alternatives: tuple[str, ...] = ()
        if project is not None:
            match = score_equipment(equipment, project.required_specifications)
            components["suitability"] = match.score
            ranked = rank_matches(catalog.equipment, project.required_specifications)
            alternatives = tuple(
                row.equipment.id
                for row in ranked
                if row.equipment.id != equipment.id and row.mandatory_ok
            )[:3]
            components["alternatives"] = float(len(alternatives))
            days = (project.deadline - now.date()).days
            components["deadline_urgency"] = -float(days)
        else:
            missing.extend(["project_deadline", "suitability", "alternatives"])

        usage = sum(
            1
            for booking in bookings
            if booking.user_id == item.user_id and booking.status is BookingStatus.APPROVED
        )
        components["fair_access"] = -float(usage)
        wait = (now - item.created_at).total_seconds()
        components["waiting"] = wait if wait >= 0 else 0.0
        raw.append(components)
        meta.append((item, eligible, feasible, tuple(missing), alternatives))

    normalized: dict[str, list[float | None]] = {}
    for key in WEIGHTS:
        column = [row[key] for row in raw]
        if key == "fair_access":
            # Lower prior usage is better; invert after min-max of the negated counts.
            pass
        normalized[key] = _minmax(column)

    scored: list[ConflictRow] = []
    for index, (item, eligible, feasible, missing, alternatives) in enumerate(meta):
        provisional = bool(missing) or any(normalized[key][index] is None for key in WEIGHTS)
        total = 0.0
        if eligible and feasible:
            for key, weight in WEIGHTS.items():
                part = normalized[key][index]
                if part is None:
                    provisional = True
                else:
                    total += weight * part
            score = round(total, 4)
        else:
            score = None
        user = users.get(item.user_id)
        scored.append(
            ConflictRow(
                request_id=item.id,
                project_id=item.project_id,
                requester_department_id=user.department_id if user is not None else "",
                requester_user_id=item.user_id if viewer_is_faculty else None,
                eligible=eligible,
                feasible=feasible,
                provisional=provisional or score is None,
                score=score,
                rank=None,
                components={key: normalized[key][index] for key in WEIGHTS},
                missing_inputs=missing,
                explanation="",
                alternatives=alternatives,
            )
        )

    eligible_rows = [row for row in scored if row.eligible and row.feasible]
    ineligible_rows = [row for row in scored if not (row.eligible and row.feasible)]
    eligible_rows.sort(key=lambda row: (-(row.score or 0.0), row.request_id))
    ineligible_rows.sort(key=lambda row: row.request_id)
    ordered = eligible_rows + ineligible_rows
    result: list[ConflictRow] = []
    for rank, row in enumerate(ordered, start=1):
        why = _explain(row, rank)
        result.append(
            ConflictRow(
                request_id=row.request_id,
                project_id=row.project_id,
                requester_department_id=row.requester_department_id,
                requester_user_id=row.requester_user_id,
                eligible=row.eligible,
                feasible=row.feasible,
                provisional=row.provisional,
                score=row.score,
                rank=rank,
                components=row.components,
                missing_inputs=row.missing_inputs,
                explanation=why,
                alternatives=row.alternatives,
            )
        )
    return result


def _explain(row: ConflictRow, rank: int) -> str:
    if not row.eligible:
        return f"Rank {rank}: ineligible under hard constraints, so it cannot win."
    if not row.feasible:
        return f"Rank {rank}: not feasible against operational status or existing bookings."
    missing = f" Missing inputs: {', '.join(row.missing_inputs)}." if row.missing_inputs else ""
    provisional = " Ranking is provisional." if row.provisional else ""
    return (
        f"Rank {rank}: weighted score {row.score} "
        f"(deadline {WEIGHTS['deadline_urgency']}, suitability {WEIGHTS['suitability']}, "
        f"fair access {WEIGHTS['fair_access']}, alternatives {WEIGHTS['alternatives']}, "
        f"waiting {WEIGHTS['waiting']}).{provisional}{missing} "
        "Faculty confirmation is required before allocation."
    )
