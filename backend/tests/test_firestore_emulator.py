"""Firestore emulator tests. Skipped when the emulator is not running."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.slots import slot_keys
from tests.conftest import FACULTY, firestore_emulator_available

pytestmark = [
    pytest.mark.firestore_emulator,
    pytest.mark.skipif(
        not firestore_emulator_available(),
        reason="Firestore emulator is not running; transaction safety is UNVERIFIED.",
    ),
]

STUDENT = {"Authorization": "Bearer test:user-student-physics"}
STUDENT_B = {"Authorization": "Bearer test:user-student-engineering"}
FACULTY_ENG = {"Authorization": "Bearer test:user-faculty-engineering"}


def _unique_slot() -> datetime:
    base = datetime(2030, 1, 6, 9, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=15 * (uuid4().int % 8000))


def _cleanup_workbench(client: TestClient) -> None:
    store = getattr(client.app.state, "bookings", None)
    fs = getattr(store, "_client", None)
    if fs is None:
        return
    for snap in fs.collection("bookings").stream():
        data = snap.to_dict() or {}
        if data.get("equipment_id") == "eq-workbench":
            snap.reference.delete()
    for snap in fs.collection("slot_locks").stream():
        data = snap.to_dict() or {}
        key = snap.id
        if data.get("equipment_id") == "eq-workbench" or key.startswith("eq-workbench_"):
            snap.reference.delete()
    workbench_request_ids = {
        snap.id
        for snap in fs.collection("access_requests").stream()
        if (snap.to_dict() or {}).get("equipment_id") == "eq-workbench"
    }
    for name in ("approvals", "allocation_decisions"):
        for snap in fs.collection(name).stream():
            data = snap.to_dict() or {}
            if data.get("request_id") in workbench_request_ids or data.get("equipment_id") == "eq-workbench":
                snap.reference.delete()
    for name in ("waitlist", "offers", "access_requests"):
        for snap in fs.collection(name).stream():
            data = snap.to_dict() or {}
            if data.get("equipment_id") == "eq-workbench":
                snap.reference.delete()


@pytest.fixture
def emulator_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("LABLINK_AUTH_MODE", "test")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-lablink")
    client = TestClient(create_app())
    _cleanup_workbench(client)
    yield client
    _cleanup_workbench(client)


def test_emulator_booking_overlap_and_adjacent(emulator_client: TestClient) -> None:
    start = _unique_slot()
    first = emulator_client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    overlap = emulator_client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": (start + timedelta(hours=1)).isoformat(),
            "end": (start + timedelta(hours=3)).isoformat(),
        },
        headers=STUDENT_B,
    )
    adjacent = emulator_client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": (start + timedelta(hours=2)).isoformat(),
            "end": (start + timedelta(hours=4)).isoformat(),
        },
        headers=STUDENT_B,
    )
    assert first.status_code == 201
    assert overlap.status_code == 409
    assert adjacent.status_code == 201
    keys = slot_keys("eq-workbench", start, start + timedelta(hours=2))
    assert keys


def test_emulator_concurrent_finalization(emulator_client: TestClient) -> None:
    start = _unique_slot()

    def attempt() -> int:
        return emulator_client.post(
            "/bookings",
            json={
                "equipment_id": "eq-workbench",
                "project_id": "proj-sensor",
                "start": start.isoformat(),
                "end": (start + timedelta(hours=2)).isoformat(),
            },
            headers=STUDENT,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(codes) == [201, 409]


def test_emulator_cancel_promote_idempotent_and_concurrent(emulator_client: TestClient) -> None:
    start = _unique_slot()
    booked = emulator_client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    assert booked.status_code == 201
    joined = emulator_client.post(
        "/waitlist",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "duration_minutes": 120,
            "preferred_start": start.isoformat(),
            "preferred_end": (start + timedelta(hours=2)).isoformat(),
            "flexibility_minutes": 0,
        },
        headers=STUDENT_B,
    )
    assert joined.status_code == 201
    cancelled = emulator_client.post(f"/bookings/{booked.json()['id']}/cancel", headers=STUDENT)
    assert cancelled.status_code == 200

    def attempt() -> tuple[int, str | None]:
        response = emulator_client.post(
            "/scheduling/promote",
            json={"equipment_id": "eq-workbench"},
            headers=FACULTY_ENG,
        )
        offer = response.json().get("offer") if response.status_code == 200 else None
        return response.status_code, offer["id"] if isinstance(offer, dict) else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert results[0][0] == 200 or results[1][0] == 200
    offer_ids = {offer_id for _, offer_id in results if offer_id}
    assert len(offer_ids) == 1


def _request_payload(start: datetime) -> dict[str, object]:
    return {
        "equipment_id": "eq-workbench",
        "project_id": "proj-sensor",
        "justification": "Emulator request for concurrent faculty decisions.",
        "start": start.isoformat(),
        "end": (start + timedelta(hours=2)).isoformat(),
    }


def test_emulator_concurrent_approve_same_request(emulator_client: TestClient) -> None:
    start = _unique_slot()
    created = emulator_client.post("/access-requests", json=_request_payload(start), headers=STUDENT)
    assert created.status_code == 201
    request_id = created.json()["id"]

    def attempt() -> int:
        return emulator_client.post(
            f"/access-requests/{request_id}/approve",
            json={"comments": "Allocate the workbench now."},
            headers=FACULTY_ENG,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(codes) == [200, 409]
    listed = emulator_client.get("/access-requests", headers=FACULTY_ENG)
    rows = [item for item in listed.json()["items"] if item["id"] == request_id]
    assert len(rows) == 1
    assert rows[0]["status"] == "approved"
    assert len(rows[0]["approvals"]) == 1
    assert rows[0]["approvals"][0]["decided_at"]
    mine = emulator_client.get("/bookings", headers=STUDENT).json()["items"]
    assert any(item["start"].startswith(start.strftime("%Y-%m-%dT%H:%M")) for item in mine)


def test_emulator_student_and_out_of_scope_cannot_decide(emulator_client: TestClient) -> None:
    start = _unique_slot()
    created = emulator_client.post("/access-requests", json=_request_payload(start), headers=STUDENT)
    request_id = created.json()["id"]
    student = emulator_client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "Self approve."},
        headers=STUDENT,
    )
    physics = emulator_client.post(
        f"/access-requests/{request_id}/reject",
        json={"comments": "Wrong department."},
        headers=FACULTY,
    )
    assert created.status_code == 201
    assert student.status_code == 403
    assert physics.status_code == 403


def test_emulator_approve_does_not_bypass_slot_lock(emulator_client: TestClient) -> None:
    start = _unique_slot()
    booked = emulator_client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    created = emulator_client.post("/access-requests", json=_request_payload(start), headers=STUDENT_B)
    approved = emulator_client.post(
        f"/access-requests/{created.json()['id']}/approve",
        json={"comments": "Slot is already held."},
        headers=FACULTY_ENG,
    )
    listed = emulator_client.get("/access-requests", headers=FACULTY_ENG)
    row = next(item for item in listed.json()["items"] if item["id"] == created.json()["id"])
    assert booked.status_code == 201
    assert created.status_code == 201
    assert approved.status_code == 409
    assert row["status"] == "pending"
    assert row["approvals"] == []


def test_emulator_concurrent_approve_and_reject(emulator_client: TestClient) -> None:
    start = _unique_slot()
    created = emulator_client.post("/access-requests", json=_request_payload(start), headers=STUDENT)
    request_id = created.json()["id"]

    def approve() -> int:
        return emulator_client.post(
            f"/access-requests/{request_id}/approve",
            json={"comments": "Take the slot."},
            headers=FACULTY_ENG,
        ).status_code

    def reject() -> int:
        return emulator_client.post(
            f"/access-requests/{request_id}/reject",
            json={"comments": "Decline this request."},
            headers=FACULTY_ENG,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda fn: fn(), [approve, reject]))
    assert sorted(codes) == [200, 409]
    listed = emulator_client.get("/access-requests", headers=FACULTY_ENG)
    row = next(item for item in listed.json()["items"] if item["id"] == request_id)
    assert row["status"] in {"approved", "rejected"}
    assert len(row["approvals"]) == 1
    assert row["approvals"][0]["decided_at"]
