"""In-memory DEMO booking engine. Each test uses a fresh app."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import STUDENT, STUDENT_B

FUTURE = datetime(2026, 12, 20, 10, 0, tzinfo=timezone.utc)


def _slot(start: datetime | None = None, hours: float = 2, **extra: object) -> dict[str, object]:
    begin = FUTURE if start is None else start
    payload: dict[str, object] = {
        "equipment_id": "eq-workbench",
        "project_id": "proj-sensor",
        "start": begin.isoformat(),
        "end": (begin + timedelta(hours=hours)).isoformat(),
    }
    payload.update(extra)
    return payload


def test_successful_booking(client: TestClient) -> None:
    response = client.post("/bookings", json=_slot(), headers=STUDENT)

    assert response.status_code == 201
    body = response.json()
    assert body["equipment_id"] == "eq-workbench"
    assert body["status"] == "approved"
    assert body["user_id"] == "user-student-physics"
    assert body["demo"] is True


def test_invalid_timestamps(client: TestClient) -> None:
    swapped = client.post(
        "/bookings",
        json=_slot(start=FUTURE + timedelta(hours=2), hours=-2),
        headers=STUDENT,
    )
    naive = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": "2026-12-20T10:00:00",
            "end": "2026-12-20T12:00:00",
        },
        headers=STUDENT,
    )

    assert swapped.status_code == 422
    assert naive.status_code == 422
    assert swapped.json()["error"] == "invalid_request"


def test_past_booking_rejected(client: TestClient) -> None:
    response = client.post(
        "/bookings",
        json=_slot(start=datetime(2020, 1, 1, 10, tzinfo=timezone.utc)),
        headers=STUDENT,
    )

    assert response.status_code == 422
    assert "past" in response.json()["message"].casefold()


def test_unknown_resources(client: TestClient) -> None:
    missing_eq = client.post("/bookings", json=_slot(equipment_id="eq-missing"), headers=STUDENT)
    missing_proj = client.post("/bookings", json=_slot(project_id="proj-missing"), headers=STUDENT)

    assert missing_eq.status_code == 404
    assert missing_proj.status_code == 404


def test_unavailable_equipment(client: TestClient) -> None:
    response = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-fume-hood", project_id="proj-hplc-method"),
        headers=STUDENT,
    )

    assert response.status_code == 409
    assert response.json()["error"] == "unavailable"


def test_overlapping_bookings(client: TestClient) -> None:
    first = client.post("/bookings", json=_slot(), headers=STUDENT)
    overlap = client.post("/bookings", json=_slot(start=FUTURE + timedelta(hours=1)), headers=STUDENT)

    assert first.status_code == 201
    assert overlap.status_code == 409
    assert overlap.json()["error"] == "conflict"


def test_adjacent_non_overlapping_slots(client: TestClient) -> None:
    first = client.post("/bookings", json=_slot(hours=2), headers=STUDENT)
    second = client.post(
        "/bookings",
        json=_slot(start=FUTURE + timedelta(hours=2), hours=2),
        headers=STUDENT,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_concurrent_conflicting_requests() -> None:
    client = TestClient(create_app())

    def attempt() -> int:
        return client.post("/bookings", json=_slot(), headers=STUDENT).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: attempt(), range(2)))

    assert sorted(codes) == [201, 409]


def test_invalid_duration(client: TestClient) -> None:
    too_short = client.post("/bookings", json=_slot(hours=0.1), headers=STUDENT)
    too_long = client.post("/bookings", json=_slot(hours=10), headers=STUDENT)

    assert too_short.status_code == 422
    assert too_long.status_code == 422


def test_restricted_equipment_without_prerequisites(client: TestClient) -> None:
    response = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-diode-laser", project_id="proj-raman"),
        headers=STUDENT,
    )

    assert response.status_code == 403
    assert response.json()["error"] == "restricted"
    assert "faculty approval" in response.json()["message"].casefold()
    listed = client.get("/bookings", headers=STUDENT)
    assert all(item["equipment_id"] != "eq-diode-laser" or item["id"] == "book-raman" for item in listed.json()["items"])
    created = [item for item in listed.json()["items"] if item["id"].startswith("book-live-")]
    assert created == []


def test_student_cannot_cancel_another_users_booking(client: TestClient) -> None:
    created = client.post("/bookings", json=_slot(), headers=STUDENT)
    stolen = client.post(f"/bookings/{created.json()['id']}/cancel", headers=STUDENT_B)
    assert created.status_code == 201
    assert stolen.status_code == 403
    listed = client.get("/bookings", headers=STUDENT)
    mine = next(item for item in listed.json()["items"] if item["id"] == created.json()["id"])
    assert mine["status"] == "approved"


def test_booking_list_is_demo_user_only(client: TestClient) -> None:
    client.post("/bookings", json=_slot(), headers=STUDENT)
    response = client.get("/bookings", headers=STUDENT)

    assert response.status_code == 200
    body = response.json()
    assert body["demo"] is True
    assert body["demo_user_id"] == "user-student-physics"
    assert {item["user_id"] for item in body["items"]} == {"user-student-physics"}
    assert "eq-oscilloscope" not in {item["equipment_id"] for item in body["items"]}


def test_availability_and_errors(client: TestClient) -> None:
    booked = client.post("/bookings", json=_slot(), headers=STUDENT)
    available = client.get(
        "/equipment/eq-workbench/availability",
        params={"date": "2026-12-20"},
        headers=STUDENT,
    )
    missing = client.get(
        "/equipment/eq-missing/availability",
        params={"date": "2026-12-20"},
        headers=STUDENT,
    )
    invalid = client.get(
        "/equipment/eq-workbench/availability",
        params={"start": FUTURE.isoformat(), "end": FUTURE.isoformat()},
        headers=STUDENT,
    )

    assert booked.status_code == 201
    assert available.status_code == 200
    body = available.json()
    assert body["demo"] is True
    assert body["source"] == "synthetic"
    busy = [(item["start"], item["end"]) for item in body["unavailable"]]
    assert any(item[0].startswith("2026-12-20T10:00:00") for item in busy)
    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "invalid_request"


def test_booked_window_is_unavailable_without_flipping_catalog_status(client: TestClient) -> None:
    booked = client.post("/bookings", json=_slot(), headers=STUDENT)
    detail = client.get("/equipment/eq-workbench")
    listed = client.get("/equipment", params={"status": "available", "search": "Open workbench"})
    available = client.get(
        "/equipment/eq-workbench/availability",
        params={"date": "2026-12-20"},
        headers=STUDENT,
    )
    overlap = client.post("/bookings", json=_slot(start=FUTURE + timedelta(hours=1)), headers=STUDENT)
    adjacent = client.post(
        "/bookings",
        json=_slot(start=FUTURE + timedelta(hours=2), hours=2),
        headers=STUDENT,
    )
    maintenance = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-fume-hood", project_id="proj-hplc-method"),
        headers=STUDENT,
    )
    still_maintenance = client.get("/equipment/eq-fume-hood")

    assert booked.status_code == 201
    assert detail.status_code == 200
    assert detail.json()["status"] == "available"
    assert listed.status_code == 200
    assert all(item["status"] == "available" for item in listed.json()["items"])
    body = available.json()
    assert [(item["start"], item["end"]) for item in body["unavailable"]] == [
        ("2026-12-20T10:00:00Z", "2026-12-20T12:00:00Z"),
    ]
    gaps = [(item["start"], item["end"]) for item in body["available"]]
    assert gaps[0][1].startswith("2026-12-20T10:00:00")
    assert gaps[-1][0].startswith("2026-12-20T12:00:00")
    assert overlap.status_code == 409
    assert overlap.json()["error"] == "conflict"
    assert adjacent.status_code == 201
    assert maintenance.status_code == 409
    assert still_maintenance.json()["status"] == "maintenance"


def test_stations_kits_and_equipment_share_slot_locks(client: TestClient) -> None:
    station = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-assembly-bench", project_id=None, purpose="Bench layout"),
        headers=STUDENT,
    )
    kit = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-electronics-kit",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
            "purpose": "Sensor wiring",
        },
        headers=STUDENT,
    )
    meter = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-handheld-multimeter"),
        headers=STUDENT,
    )
    overlap_kit = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-electronics-kit", start=FUTURE + timedelta(hours=1)),
        headers=STUDENT,
    )
    adjacent_kit = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-electronics-kit", start=FUTURE + timedelta(hours=2)),
        headers=STUDENT,
    )
    laser_kit = client.post(
        "/bookings",
        json=_slot(equipment_id="eq-laser-kit", project_id="proj-raman"),
        headers=STUDENT,
    )

    assert station.status_code == 201
    assert station.json()["kind"] == "lab-station"
    assert station.json()["equipment_name"] == "Electronics assembly bench"
    assert station.json()["purpose"] == "Bench layout"
    assert kit.status_code == 201
    assert kit.json()["kind"] == "kit"
    assert meter.status_code == 201
    assert meter.json()["kind"] == "equipment"
    assert overlap_kit.status_code == 409
    assert adjacent_kit.status_code == 201
    assert laser_kit.status_code == 403
    assert "faculty approval" in laser_kit.json()["message"].casefold()
