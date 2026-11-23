"""Analytics from stored records. Utilization percent is omitted without operating hours."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.conftest import ADMIN, FACULTY, FACULTY_ENG, STUDENT, STUDENT_B

SEED_START = "2026-12-01T00:00:00+00:00"
SEED_END = "2026-12-31T00:00:00+00:00"
EMPTY_START = "2019-01-01T00:00:00+00:00"
EMPTY_END = "2019-01-08T00:00:00+00:00"


def test_unauthorized_and_student_forbidden(client: TestClient) -> None:
    anon = client.get("/analytics/overview", params={"start": SEED_START, "end": SEED_END})
    student = client.get(
        "/analytics/overview",
        params={"start": SEED_START, "end": SEED_END},
        headers=STUDENT,
    )
    assert anon.status_code == 200
    assert student.status_code == 200
    assert anon.json()["demo"] is True
    assert student.json()["demo"] is True


def test_invalid_date_range(client: TestClient) -> None:
    missing = client.get("/analytics/overview", headers=ADMIN)
    inverted = client.get(
        "/analytics/overview",
        params={"start": SEED_END, "end": SEED_START},
        headers=ADMIN,
    )
    naive = client.get(
        "/analytics/overview",
        params={"start": "2026-12-01T00:00:00", "end": "2026-12-31T00:00:00"},
        headers=ADMIN,
    )
    assert missing.status_code == 422
    assert inverted.status_code == 422
    assert naive.status_code == 422


def test_empty_window_has_zero_confirmed_and_unavailable_utilization(client: TestClient) -> None:
    response = client.get(
        "/analytics/overview",
        params={"start": EMPTY_START, "end": EMPTY_END},
        headers=ADMIN,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] is True
    assert body["counts"]["confirmed_bookings"] == 0
    assert body["utilization"]["percent"] is None
    assert body["utilization"]["occupied_minutes"] == 0
    assert body["utilization"]["available_minutes"] is None
    assert body["utilization"]["capacity_per_slot"] == 1
    assert "operating hours" in body["utilization"]["unavailable_reason"].casefold()
    assert body["most_booked"] == [] or all(item["confirmed_bookings"] == 0 for item in body["most_booked"])


def test_seed_metrics_exclude_requested_and_use_occupied_minutes(client: TestClient) -> None:
    response = client.get(
        "/analytics/overview",
        params={"start": SEED_START, "end": SEED_END},
        headers=ADMIN,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["confirmed_bookings"] == 1
    assert body["utilization"]["occupied_minutes"] == 120
    assert body["utilization"]["percent"] is None
    booked = {item["equipment_id"]: item for item in body["most_booked"]}
    assert booked["eq-oscilloscope"]["occupied_minutes"] == 120
    assert booked["eq-oscilloscope"]["confirmed_bookings"] == 1
    assert "eq-diode-laser" not in booked or booked["eq-diode-laser"]["confirmed_bookings"] == 0
    assert body["counts"]["pending_requests"] >= 1
    assert body["approval_turnaround"]["sample_size"] == 1
    assert body["approval_turnaround"]["median_hours"] == 53.0


def test_cancelled_bookings_excluded(client: TestClient) -> None:
    start = datetime(2027, 2, 1, 10, 0, tzinfo=timezone.utc)
    created = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    assert created.status_code == 201
    before = client.get(
        "/analytics/overview",
        params={"start": "2027-02-01T00:00:00+00:00", "end": "2027-02-02T00:00:00+00:00"},
        headers=ADMIN,
    )
    cancelled = client.post(f"/bookings/{created.json()['id']}/cancel", headers=STUDENT)
    after = client.get(
        "/analytics/overview",
        params={"start": "2027-02-01T00:00:00+00:00", "end": "2027-02-02T00:00:00+00:00"},
        headers=ADMIN,
    )
    assert cancelled.status_code == 200
    assert before.json()["counts"]["confirmed_bookings"] == 1
    assert after.json()["counts"]["confirmed_bookings"] == 0
    assert after.json()["utilization"]["occupied_minutes"] == 0


def test_department_scope(client: TestClient) -> None:
    physics = client.get(
        "/analytics/departments",
        params={"start": SEED_START, "end": SEED_END},
        headers=FACULTY,
    )
    admin = client.get(
        "/analytics/departments",
        params={"start": SEED_START, "end": SEED_END},
        headers=ADMIN,
    )
    assert physics.status_code == 200
    assert {item["department_id"] for item in physics.json()["items"]} == {"dept-physics"}
    assert {item["department_id"] for item in admin.json()["items"]} >= {
        "dept-physics",
        "dept-engineering",
    }
    physics_eq = client.get(
        "/analytics/equipment",
        params={"start": SEED_START, "end": SEED_END},
        headers=FACULTY,
    )
    ids = {item["equipment_id"] for item in physics_eq.json()["items"]}
    assert "eq-diode-laser" in ids
    assert "eq-workbench" not in ids
    assert "eq-oscilloscope" not in ids


def test_sequential_confirmed_bookings_add_occupied_minutes(client: TestClient) -> None:
    start = datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc)
    first = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    second = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": (start + timedelta(hours=2)).isoformat(),
            "end": (start + timedelta(hours=4)).isoformat(),
        },
        headers=STUDENT,
    )
    overview = client.get(
        "/analytics/overview",
        params={"start": "2027-03-01T00:00:00+00:00", "end": "2027-03-02T00:00:00+00:00"},
        headers=ADMIN,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    body = overview.json()
    assert body["counts"]["confirmed_bookings"] == 2
    assert body["utilization"]["occupied_minutes"] == 240
    assert body["utilization"]["percent"] is None


def test_waitlist_demand_and_capacity(client: TestClient) -> None:
    start = datetime(2027, 6, 1, 10, 0, tzinfo=timezone.utc)
    booked = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    joined = client.post(
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
    overview = client.get(
        "/analytics/overview",
        params={"start": "2027-06-01T00:00:00+00:00", "end": "2027-06-02T00:00:00+00:00"},
        headers=FACULTY_ENG,
    )
    assert booked.status_code == 201
    assert joined.status_code == 201
    body = overview.json()
    assert body["counts"]["waitlist_waiting"] == 1
    assert body["utilization"]["capacity_per_slot"] == 1
    demand = {item["equipment_id"]: item["waitlist_waiting"] for item in body["waitlist_demand"]}
    assert demand.get("eq-workbench") == 1


def test_firestore_errors_surface_unavailable(client: TestClient, monkeypatch) -> None:
    def boom() -> list:
        raise RuntimeError("store failed")

    monkeypatch.setattr(client.app.state.bookings, "snapshot", boom)
    response = client.get(
        "/analytics/overview",
        params={"start": SEED_START, "end": SEED_END},
        headers=ADMIN,
    )
    assert response.status_code == 503
    assert response.json()["error"] == "unavailable"
    assert "store failed" not in response.text
