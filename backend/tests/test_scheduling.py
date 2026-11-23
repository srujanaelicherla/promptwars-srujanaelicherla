"""Advisory scheduling recommendations. Slots are not holds."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.conftest import STUDENT

FUTURE = datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc)


def _body(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "equipment_id": "eq-workbench",
        "project_id": "proj-sensor",
        "duration_minutes": 120,
        "preferred_start": FUTURE.isoformat(),
        "preferred_end": (FUTURE + timedelta(hours=4)).isoformat(),
        "flexibility_minutes": 0,
        "increment_minutes": 15,
    }
    payload.update(extra)
    return payload


def test_recommendations_are_advisory_and_utc(client: TestClient) -> None:
    response = client.post("/scheduling/recommendations", json=_body(), headers=STUDENT)
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] is True
    assert body["slots"]
    first = body["slots"][0]
    assert first["advisory"] is True
    assert first["equipment_id"] == "eq-workbench"
    assert "not a hold" in first["explanation"].casefold()
    assert any("operating hours" in item.casefold() for item in body["constraints"])
    assert any("maintenance windows" in item.casefold() for item in body["constraints"])
    listed = client.get("/bookings", headers=STUDENT)
    created = [item for item in listed.json()["items"] if item["id"].startswith("book-") and item["start"].startswith("2027-03-01")]
    assert created == []


def test_invalid_scheduling_input(client: TestClient) -> None:
    anon = client.post("/scheduling/recommendations", json=_body())
    naive = client.post(
        "/scheduling/recommendations",
        json=_body(preferred_start="2027-03-01T10:00:00", preferred_end="2027-03-01T14:00:00"),
        headers=STUDENT,
    )
    increment = client.post("/scheduling/recommendations", json=_body(increment_minutes=45), headers=STUDENT)
    duration = client.post("/scheduling/recommendations", json=_body(duration_minutes=20), headers=STUDENT)
    missing = client.post("/scheduling/recommendations", json=_body(equipment_id="eq-missing"), headers=STUDENT)
    assert anon.status_code == 401
    assert naive.status_code == 422
    assert increment.status_code == 422
    assert duration.status_code == 422
    assert missing.status_code == 404


def test_maintenance_has_no_slots_and_known_alternatives(client: TestClient) -> None:
    response = client.post(
        "/scheduling/recommendations",
        json=_body(equipment_id="eq-fume-hood", project_id="proj-hplc-method"),
        headers=STUDENT,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["slots"] == []
    assert body["waitlist_eligible"] is True
    assert any("maintenance" in item.casefold() for item in body["constraints"])
    ids = {item["equipment_id"] for item in body["alternatives"]}
    assert "eq-fume-hood" not in ids
    assert "eq-invented" not in ids
    assert all(item["mandatory_ok"] is True for item in body["alternatives"])


def test_conflicts_excluded_and_booking_still_revalidates(client: TestClient) -> None:
    booked = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    rec = client.post(
        "/scheduling/recommendations",
        json=_body(preferred_end=(FUTURE + timedelta(hours=2)).isoformat()),
        headers=STUDENT,
    )
    assert booked.status_code == 201
    assert rec.status_code == 200
    starts = {item["start"] for item in rec.json()["slots"]}
    assert not any(item.startswith("2027-03-01T10:00:00") for item in starts)
    overlap = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    assert overlap.status_code == 409
