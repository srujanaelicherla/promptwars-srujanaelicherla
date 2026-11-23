"""DEMO access requests, faculty decisions, and conflict ranking."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.conflicts import evaluate_conflicts
from app.main import create_app
from app.models import AccessRequest, RequestStatus
from app.seed import load_seed
from tests.conftest import FACULTY, FACULTY_CHEM, FACULTY_ENG, STUDENT, STUDENT_B

FUTURE = datetime(2026, 12, 22, 10, 0, tzinfo=timezone.utc)


def _payload(**extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "equipment_id": "eq-workbench",
        "project_id": "proj-sensor",
        "justification": "DEMO request for the open workbench.",
        "start": FUTURE.isoformat(),
        "end": (FUTURE + timedelta(hours=2)).isoformat(),
    }
    body.update(extra)
    return body


def test_request_submission(client: TestClient) -> None:
    response = client.post("/access-requests", json=_payload(), headers=STUDENT)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["user_id"] == "user-student-physics"
    assert body["demo"] is True


def test_invalid_requests(client: TestClient) -> None:
    missing = client.post("/access-requests", json=_payload())
    faculty = client.post("/access-requests", json=_payload(), headers=FACULTY)
    past = client.post(
        "/access-requests",
        json=_payload(start="2020-01-01T10:00:00+00:00", end="2020-01-01T12:00:00+00:00"),
        headers=STUDENT,
    )
    unknown = client.post("/access-requests", json=_payload(equipment_id="eq-missing"), headers=STUDENT)

    assert missing.status_code == 401
    assert faculty.status_code == 403
    assert past.status_code == 422
    assert unknown.status_code == 404


def test_valid_status_transitions_and_duplicate_approvals(client: TestClient) -> None:
    created = client.post("/access-requests", json=_payload(), headers=STUDENT)
    request_id = created.json()["id"]
    approved = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "Slot is free on the workbench."},
        headers=FACULTY_ENG,
    )
    duplicate = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "Second look."},
        headers=FACULTY_ENG,
    )
    reject_after = client.post(
        f"/access-requests/{request_id}/reject",
        json={"comments": "Too late."},
        headers=FACULTY_ENG,
    )

    assert created.status_code == 201
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["booking_id"]
    assert duplicate.status_code == 409
    assert reject_after.status_code == 409


def test_physics_faculty_cannot_approve_engineering_request(client: TestClient) -> None:
    created = client.post("/access-requests", json=_payload(), headers=STUDENT)
    request_id = created.json()["id"]
    physics = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "Wrong department."},
        headers=FACULTY,
    )
    assert created.status_code == 201
    assert physics.status_code == 403
    assert physics.json()["error"] == "forbidden"


def test_unauthorized_and_missing_identity(client: TestClient) -> None:
    created = client.post("/access-requests", json=_payload(), headers=STUDENT)
    request_id = created.json()["id"]
    as_student = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "No."},
        headers=STUDENT,
    )
    anonymous = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "No."},
    )
    unknown = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "No."},
        headers={"Authorization": "Bearer test:user-nobody"},
    )

    assert as_student.status_code == 403
    assert anonymous.status_code == 401
    assert unknown.status_code == 401


def test_deadline_fairness_missing_inputs_and_ties() -> None:
    catalog = load_seed()
    workbench = next(item for item in catalog.equipment if item.id == "eq-workbench")
    now = datetime(2026, 11, 23, tzinfo=timezone.utc)
    early = AccessRequest(
        id="req-early",
        user_id="user-student-physics",
        project_id="proj-sensor",
        equipment_id="eq-workbench",
        justification="Earlier deadline project.",
        status=RequestStatus.PENDING,
        created_at=now,
        start=FUTURE,
        end=FUTURE + timedelta(hours=2),
    )
    late = AccessRequest(
        id="req-late",
        user_id="user-student-engineering",
        project_id="proj-hplc-method",
        equipment_id="eq-workbench",
        justification="Later deadline project.",
        status=RequestStatus.PENDING,
        created_at=now,
        start=FUTURE,
        end=FUTURE + timedelta(hours=2),
    )
    ranked = evaluate_conflicts(
        catalog=catalog,
        equipment=workbench,
        requests=[late, early],
        bookings=catalog.bookings,
        now=now,
        viewer_is_faculty=True,
    )
    assert [row.request_id for row in ranked] == ["req-early", "req-late"]
    assert ranked[0].score is not None and ranked[1].score is not None
    assert ranked[0].score >= ranked[1].score
    assert ranked[0].requester_user_id == "user-student-physics"

    again = evaluate_conflicts(
        catalog=catalog,
        equipment=workbench,
        requests=[early, late],
        bookings=catalog.bookings,
        now=now,
        viewer_is_faculty=False,
    )
    assert [row.request_id for row in again] == [row.request_id for row in ranked]
    assert again[0].requester_user_id is None

    no_slot = early.model_copy(update={"id": "req-open", "start": None, "end": None})
    open_rank = evaluate_conflicts(
        catalog=catalog,
        equipment=workbench,
        requests=[no_slot],
        bookings=[],
        now=now,
        viewer_is_faculty=True,
    )
    assert "requested_slot" in open_rank[0].missing_inputs
    assert open_rank[0].provisional is True


def test_ineligible_maintenance_cannot_win(client: TestClient) -> None:
    created = client.post(
        "/access-requests",
        json=_payload(equipment_id="eq-fume-hood", project_id="proj-hplc-method"),
        headers=STUDENT_B,
    )
    conflicts = client.get("/equipment/eq-fume-hood/conflicts", headers=FACULTY_CHEM)

    assert created.status_code == 201
    row = next(item for item in conflicts.json()["items"] if item["request_id"] == created.json()["id"])
    assert row["feasible"] is False
    assert row["score"] is None


def test_conflicting_bookings_and_concurrent_finalization() -> None:
    client = TestClient(create_app())
    first = client.post("/access-requests", json=_payload(), headers=STUDENT)
    second = client.post("/access-requests", json=_payload(), headers=STUDENT_B)
    assert first.status_code == 201
    assert second.status_code == 201
    ids = [first.json()["id"], second.json()["id"]]

    def approve(request_id: str) -> int:
        return client.post(
            f"/access-requests/{request_id}/approve",
            json={"comments": "Allocate the workbench."},
            headers=FACULTY_ENG,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(approve, ids))

    assert sorted(codes) == [200, 409]


def test_student_list_hides_others(client: TestClient) -> None:
    client.post("/access-requests", json=_payload(), headers=STUDENT)
    client.post("/access-requests", json=_payload(), headers=STUDENT_B)
    own = client.get("/access-requests", headers=STUDENT)
    faculty = client.get("/access-requests", headers=FACULTY_ENG)
    conflicts_student = client.get("/equipment/eq-workbench/conflicts", headers=STUDENT)

    assert own.status_code == 200
    assert {item["user_id"] for item in own.json()["items"] if item["user_id"]} <= {"user-student-physics"}
    assert faculty.status_code == 200
    assert len(faculty.json()["items"]) >= 2
    assert conflicts_student.status_code == 403
