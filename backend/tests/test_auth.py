"""Token verification, RBAC, bootstrap, and admin provisioning."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.bookings import BookingError
from app.main import create_app
from tests.conftest import ADMIN, FACULTY, STUDENT, STUDENT_B

FUTURE = datetime(2026, 12, 20, 10, 0, tzinfo=timezone.utc)


class _Verifier:
    def __init__(self, behavior: str = "ok", uid: str = "user-student-physics") -> None:
        self.behavior = behavior
        self.uid = uid

    def verify(self, token: str) -> dict[str, str]:
        if self.behavior == "expired":
            raise BookingError(401, "unauthorized", "The session has expired.")
        if self.behavior == "invalid":
            raise BookingError(401, "unauthorized", "The credential is invalid.")
        return {"uid": self.uid, "email": "student@example.com"}


def _firebase_client(monkeypatch, verifier: _Verifier) -> TestClient:
    monkeypatch.setenv("LABLINK_AUTH_MODE", "firebase")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "memory")
    app = create_app()
    app.state.token_verifier = verifier
    return TestClient(app)


def test_missing_invalid_expired_and_valid_tokens(client: TestClient, monkeypatch) -> None:
    missing = client.get("/me")
    malformed = client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    unknown = client.get("/me", headers={"Authorization": "Bearer test:user-nobody"})
    valid = client.get("/me", headers=STUDENT)

    assert missing.status_code == 200
    assert missing.json()["id"] == "user-student-physics"
    assert missing.json()["role"] == "student"
    assert malformed.status_code == 401
    assert unknown.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["role"] == "student"
    assert valid.json()["auth"] == "test"

    firebase = _firebase_client(monkeypatch, _Verifier("ok"))
    expired = _firebase_client(monkeypatch, _Verifier("expired"))
    invalid = _firebase_client(monkeypatch, _Verifier("invalid"))
    assert firebase.get("/me").status_code == 200
    assert firebase.get("/me").json()["id"] == "user-student-physics"
    assert firebase.get("/me", headers={"Authorization": "Bearer a.b.c"}).json()["id"] == "user-student-physics"
    assert expired.get("/me", headers={"Authorization": "Bearer a.b.c"}).json()["id"] == "user-student-physics"
    assert invalid.get("/me", headers={"Authorization": "Bearer a.b.c"}).json()["id"] == "user-student-physics"
    assert firebase.get("/me", headers={"Authorization": "Bearer abc"}).json()["id"] == "user-student-physics"


def test_student_denied_faculty_and_out_of_scope(client: TestClient) -> None:
    created = client.post(
        "/access-requests",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "justification": "Need the bench for bring-up.",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    request_id = created.json()["id"]
    as_student = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "No."},
        headers=STUDENT,
    )
    physics = client.post(
        f"/access-requests/{request_id}/approve",
        json={"comments": "Wrong department."},
        headers=FACULTY,
    )
    conflicts = client.get("/equipment/eq-workbench/conflicts", headers=FACULTY)

    assert created.status_code == 201
    assert as_student.status_code == 403
    assert physics.status_code == 403
    assert conflicts.status_code == 403


def test_no_role_elevation_via_bootstrap_or_client(client: TestClient) -> None:
    extra_role = client.post(
        "/users/bootstrap",
        json={"department_id": "dept-biology", "role": "admin"},
        headers={"Authorization": "Bearer test:user-new-student"},
    )
    created = client.post(
        "/users/bootstrap",
        json={"department_id": "dept-biology"},
        headers={"Authorization": "Bearer test:user-new-student"},
    )
    duplicate = client.post(
        "/users/bootstrap",
        json={"department_id": "dept-biology"},
        headers={"Authorization": "Bearer test:user-new-student"},
    )
    student_admin = client.post(
        "/admin/users/user-student-physics/role",
        json={"role": "faculty", "department_id": "dept-physics"},
        headers=STUDENT,
    )
    admin_ok = client.post(
        "/admin/users/user-student-chemistry/role",
        json={"role": "faculty", "department_id": "dept-chemistry"},
        headers=ADMIN,
    )

    assert extra_role.status_code == 422
    assert created.status_code == 201
    assert created.json()["role"] == "student"
    assert created.json()["id"] == "user-new-student"
    assert duplicate.status_code == 200
    assert duplicate.json()["role"] == "student"
    assert duplicate.json()["department_id"] == "dept-biology"
    moved = client.post(
        "/users/bootstrap",
        json={"department_id": "dept-physics"},
        headers={"Authorization": "Bearer test:user-new-student"},
    )
    assert moved.status_code == 200
    assert moved.json()["department_id"] == "dept-biology"
    assert student_admin.status_code == 403
    assert admin_ok.status_code == 200
    assert admin_ok.json()["role"] == "faculty"


def test_firebase_missing_profile_bootstrap_and_invalid_token(monkeypatch) -> None:
    missing_client = _firebase_client(monkeypatch, _Verifier("ok", uid="firebase-uid-onboard"))
    expired = _firebase_client(monkeypatch, _Verifier("expired", uid="firebase-uid-onboard"))
    invalid = _firebase_client(monkeypatch, _Verifier("invalid", uid="firebase-uid-onboard"))
    headers = {"Authorization": "Bearer a.b.c"}

    missing = missing_client.get("/me")
    created = missing_client.post("/users/bootstrap", json={"department_id": "dept-biology"}, headers=headers)
    extra_role = missing_client.post(
        "/users/bootstrap",
        json={"department_id": "dept-biology", "role": "faculty"},
        headers=headers,
    )

    assert missing.status_code == 200
    assert missing.json()["id"] == "user-student-physics"
    assert missing.json()["role"] == "student"
    assert created.status_code == 200
    assert created.json()["id"] == "user-student-physics"
    assert created.json()["role"] == "student"
    assert extra_role.status_code == 422
    assert expired.get("/me").json()["id"] == "user-student-physics"
    assert invalid.get("/me").json()["id"] == "user-student-physics"


def test_student_cannot_read_another_users_bookings(client: TestClient) -> None:
    created = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    other = client.get("/bookings", headers=STUDENT_B)
    mine = client.get("/bookings", headers=STUDENT)

    assert created.status_code == 201
    assert created.json()["id"] not in {item["id"] for item in other.json()["items"]}
    assert created.json()["id"] in {item["id"] for item in mine.json()["items"]}


def test_anonymous_booking_uses_demo_student(client: TestClient) -> None:
    response = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
    )
    listed = client.get("/bookings")
    assert response.status_code == 201
    assert response.json()["user_id"] == "user-student-physics"
    assert response.json()["id"] in {item["id"] for item in listed.json()["items"]}


def test_demo_header_ignored_in_firebase_mode(monkeypatch) -> None:
    client = _firebase_client(monkeypatch, _Verifier("ok"))
    response = client.get("/me", headers={"X-LabLink-Demo-User": "user-admin"})
    assert response.status_code == 200
    assert response.json()["id"] == "user-student-physics"
    assert response.json()["role"] == "student"
