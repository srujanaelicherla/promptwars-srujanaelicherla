"""Validation and synthetic-seed integrity. No API or booking behavior."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import Booking, BookingStatus, EquipmentStatus, Role, Specification, User
from app.seed import Catalog, load_seed


def _booking(**overrides: object) -> dict[str, object]:
    start = datetime(2026, 12, 2, 9, tzinfo=timezone.utc)
    end = datetime(2026, 12, 2, 11, tzinfo=timezone.utc)
    values: dict[str, object] = {
        "id": "book-sample",
        "user_id": "user-student-physics",
        "equipment_id": "eq-diode-laser",
        "project_id": "proj-raman",
        "start": start,
        "end": end,
        "status": BookingStatus.REQUESTED,
    }
    values.update(overrides)
    return values


def test_seed_shape_is_synthetic_and_complete() -> None:
    catalog = load_seed()

    assert catalog.synthetic is True
    assert len(catalog.departments) == 4
    assert len(catalog.labs) == 4
    assert len(catalog.equipment) == 110
    assert len(catalog.projects) == 4
    assert {user.role for user in catalog.users} == {Role.ADMIN, Role.FACULTY, Role.STUDENT}
    assert catalog.bookings
    assert catalog.access_requests
    assert catalog.approvals


def test_seed_references_match() -> None:
    catalog = load_seed()
    labs = {lab.id: lab for lab in catalog.labs}
    users = {user.id: user for user in catalog.users}
    request_ids = {item.id for item in catalog.access_requests}

    for item in catalog.equipment:
        assert item.specifications
        assert item.department_id == labs[item.lab_id].department_id
        if item.kind.value == "equipment" and item.id != "eq-handheld-multimeter":
            assert item.safety_prerequisites
        if item.kind.value in {"lab-station", "kit"} and item.id != "eq-laser-kit":
            assert not item.safety_prerequisites
    for approval in catalog.approvals:
        assert approval.request_id in request_ids
        assert users[approval.faculty_id].role is Role.FACULTY


def test_catalog_rejects_dangling_and_non_faculty_links() -> None:
    payload = load_seed().model_dump(mode="json")
    dangling = {**payload, "equipment": [{**payload["equipment"][0], "lab_id": "lab-missing"}, *payload["equipment"][1:]]}
    with pytest.raises(ValidationError, match="unknown id"):
        Catalog.model_validate(dangling)

    non_faculty = {
        **payload,
        "approvals": [{**payload["approvals"][0], "faculty_id": "user-student-physics"}],
    }
    with pytest.raises(ValidationError, match="not a faculty user"):
        Catalog.model_validate(non_faculty)


def test_catalog_rejects_user_when_canonical_department_is_missing() -> None:
    payload = load_seed().model_dump(mode="json")
    payload["departments"] = []
    payload["labs"] = []
    payload["equipment"] = []
    payload["projects"] = []
    payload["bookings"] = []
    payload["access_requests"] = []
    payload["approvals"] = []
    payload["allocation_decisions"] = []
    payload["users"] = [
        {"id": "user-fixture", "role": "student", "department_id": "dept-physics"},
    ]
    with pytest.raises(ValidationError, match="user references unknown id dept-physics"):
        Catalog.model_validate(payload)


def test_booking_times_must_be_aware_and_ordered() -> None:
    with pytest.raises(ValidationError, match="end must be after start"):
        Booking(**_booking(end=datetime(2026, 12, 2, 9, tzinfo=timezone.utc)))
    with pytest.raises(ValidationError, match="end must be after start"):
        Booking(**_booking(end=datetime(2026, 12, 2, 8, tzinfo=timezone.utc)))
    with pytest.raises(ValidationError):
        Booking(**_booking(start=datetime(2026, 12, 2, 9)))


def test_invalid_status_role_and_specification_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Booking(**_booking(status="reserved"))
    with pytest.raises(ValidationError):
        User(id="user-guest", role="guest", department_id="dept-physics")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        User(id="Not An Id", role=Role.STUDENT, department_id="dept-physics")
    with pytest.raises(ValidationError):
        Specification(name=" ", value="532", unit="nm")

    equipment = load_seed().model_dump(mode="json")["equipment"][0]
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                **load_seed().model_dump(mode="json"),
                "equipment": [{**equipment, "specifications": []}, *load_seed().model_dump(mode="json")["equipment"][1:]],
            }
        )
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                **load_seed().model_dump(mode="json"),
                "equipment": [{**equipment, "status": "in_use"}, *load_seed().model_dump(mode="json")["equipment"][1:]],
            }
        )


def test_equipment_status_enum_accepts_only_catalog_states() -> None:
    with pytest.raises(ValueError):
        EquipmentStatus("in_use")
