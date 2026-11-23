"""Match project requirements to catalog equipment specifications.

Score = round(matched_count / requirement_count, 4) in [0, 1].

Classification: fully_suitable when every requirement matches;
partially_suitable when some match; unsuitable when none match.

Hard constraints: Requirement.mandatory must match. A failure cannot be
fully_suitable and is ranked below every item that meets all mandatory
requirements, regardless of score. Rank is then classification, then score
descending, then equipment id.

Numeric values parse as a number or inclusive 'min-max' interval and convert
to a canonical unit. equal: required interval is inside the equipment interval.
at_least: equipment max >= required min. at_most: equipment min <= required max.
A missing spec, a missing unit when the other side has a unit, or incompatible
units do not match. Categorical values use casefolded, whitespace-normalized
equality or comma-set membership.

This uses recorded catalog specs only. It does not invent capabilities or
assess live availability or booking.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.models import (
    Equipment,
    Requirement,
    SpecComparison,
    Specification,
    Suitability,
)

_NUMBER = r"\d+(?:\.\d+)?"
_RANGE = re.compile(rf"^({_NUMBER})\s*-\s*({_NUMBER})$")
_POINT = re.compile(rf"^({_NUMBER})$")

# (family, factor to canonical). Families never convert across each other.
_UNITS: dict[str, tuple[str, float]] = {
    "m": ("length", 1.0),
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "nm": ("length", 1e-9),
    "w": ("power", 1.0),
    "mw": ("power", 0.001),
    "hz": ("frequency", 1.0),
    "khz": ("frequency", 1e3),
    "mhz": ("frequency", 1e6),
    "ghz": ("frequency", 1e9),
    "gsa/s": ("frequency", 1e9),
    "ml/min": ("flow", 1.0),
    "l/min": ("flow", 1000.0),
    "mpa": ("pressure", 1.0),
    "kpa": ("pressure", 0.001),
    "g": ("mass", 1.0),
    "mg": ("mass", 0.001),
    "kg": ("mass", 1000.0),
    "m/s": ("speed", 1.0),
    "rpm": ("rotation", 1.0),
}


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float
    family: str | None


@dataclass(frozen=True)
class MatchResult:
    equipment: Equipment
    score: float
    suitability: Suitability
    mandatory_ok: bool
    matched_requirements: tuple[str, ...]
    unmet_requirements: tuple[str, ...]
    explanation: str


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def normalize_label(value: str) -> str:
    return " ".join(value.casefold().split())


def _unit_key(unit: str) -> str:
    return unit.casefold().strip()


def _parse_interval(value: str, unit: str | None) -> Interval | None:
    text = value.strip()
    ranged = _RANGE.fullmatch(text)
    point = _POINT.fullmatch(text)
    if ranged is not None:
        lo, hi = float(ranged.group(1)), float(ranged.group(2))
    elif point is not None:
        lo = hi = float(point.group(1))
    else:
        return None
    if lo > hi:
        return None
    if unit is None:
        return Interval(lo, hi, None)
    known = _UNITS.get(_unit_key(unit))
    if known is None:
        return None
    family, factor = known
    return Interval(lo * factor, hi * factor, family)


def _categorical_match(required: str, actual: str) -> bool:
    want = normalize_label(required)
    members = [normalize_label(part) for part in actual.split(",")]
    return want in members


def requirement_matches(requirement: Requirement, spec: Specification) -> bool:
    """Return whether one equipment spec satisfies one requirement."""

    required = _parse_interval(requirement.value, requirement.unit)
    actual = _parse_interval(spec.value, spec.unit)
    if required is None and actual is None:
        return _categorical_match(requirement.value, spec.value)
    if required is None or actual is None:
        return False
    if (required.family is None) != (actual.family is None):
        return False
    if required.family is not None and required.family != actual.family:
        return False
    if requirement.comparison is SpecComparison.EQUAL:
        return actual.lo <= required.lo and required.hi <= actual.hi
    if requirement.comparison is SpecComparison.AT_LEAST:
        return actual.hi >= required.lo
    if requirement.comparison is SpecComparison.AT_MOST:
        return actual.lo <= required.hi
    return False


def _find_spec(equipment: Equipment, name: str) -> Specification | None:
    wanted = normalize_name(name)
    for spec in equipment.specifications:
        if normalize_name(spec.name) == wanted:
            return spec
    return None


def _classify(matched: int, total: int) -> Suitability:
    if matched == total:
        return Suitability.FULLY_SUITABLE
    if matched == 0:
        return Suitability.UNSUITABLE
    return Suitability.PARTIALLY_SUITABLE


def _explain(equipment: Equipment, result: MatchResult) -> str:
    matched = ", ".join(result.matched_requirements) or "none"
    unmet = ", ".join(result.unmet_requirements) or "none"
    return (
        f"{equipment.name} is {result.suitability.value.replace('_', ' ')} "
        f"(score {result.score}). Matched: {matched}. Unmet: {unmet}. "
        "Catalog specifications only; not live availability."
    )


def score_equipment(equipment: Equipment, requirements: list[Requirement]) -> MatchResult:
    if not requirements:
        raise ValueError("at least one requirement is required")

    matched: list[str] = []
    unmet: list[str] = []
    mandatory_ok = True
    for requirement in requirements:
        spec = _find_spec(equipment, requirement.name)
        ok = spec is not None and requirement_matches(requirement, spec)
        if ok:
            matched.append(requirement.name)
        else:
            unmet.append(requirement.name)
            if requirement.mandatory:
                mandatory_ok = False

    suitability = _classify(len(matched), len(requirements))
    if not mandatory_ok and suitability is Suitability.FULLY_SUITABLE:
        suitability = Suitability.PARTIALLY_SUITABLE
    draft = MatchResult(
        equipment=equipment,
        score=round(len(matched) / len(requirements), 4),
        suitability=suitability,
        mandatory_ok=mandatory_ok,
        matched_requirements=tuple(matched),
        unmet_requirements=tuple(unmet),
        explanation="",
    )
    return MatchResult(
        equipment=draft.equipment,
        score=draft.score,
        suitability=draft.suitability,
        mandatory_ok=draft.mandatory_ok,
        matched_requirements=draft.matched_requirements,
        unmet_requirements=draft.unmet_requirements,
        explanation=_explain(equipment, draft),
    )


def rank_matches(equipment: list[Equipment], requirements: list[Requirement]) -> list[MatchResult]:
    """Score every candidate and return a stable ranking."""

    ranked = [score_equipment(item, requirements) for item in equipment]
    class_order = {
        Suitability.FULLY_SUITABLE: 0,
        Suitability.PARTIALLY_SUITABLE: 1,
        Suitability.UNSUITABLE: 2,
    }
    ranked.sort(
        key=lambda item: (
            0 if item.mandatory_ok else 1,
            class_order[item.suitability],
            -item.score,
            item.equipment.id,
        )
    )
    return ranked
