"""Health route behavior."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_success_shape_and_headers(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok", "service": "lablink-api"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in response.headers


def test_health_ignores_unrelated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABLINK_SERVICE_NAME", "lab-west")
    monkeypatch.setenv("SECRET_TOKEN", "should-not-leak")

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "lab-west"}
    assert "should-not-leak" not in response.text


def test_invalid_service_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABLINK_SERVICE_NAME", "Bad=secret")

    with pytest.raises(ValueError, match="^LABLINK_SERVICE_NAME must be a lowercase identifier$"):
        create_app()


def test_openapi_lists_application_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == {
        "/health",
        "/equipment",
        "/equipment/{equipment_id}",
        "/projects/{project_id}/equipment-matches",
        "/equipment/{equipment_id}/availability",
        "/bookings",
        "/access-requests",
        "/access-requests/{request_id}/approve",
        "/access-requests/{request_id}/reject",
        "/equipment/{equipment_id}/conflicts",
        "/me",
        "/users/bootstrap",
        "/admin/users/{user_id}/role",
        "/ai/project-requirements",
        "/ai/assistant/query",
        "/ai/equipment-explanation",
        "/scheduling/recommendations",
        "/scheduling/promote",
        "/waitlist",
        "/waitlist/{entry_id}/cancel",
        "/waitlist/{entry_id}/accept",
        "/bookings/{booking_id}/cancel",
        "/analytics/overview",
        "/analytics/departments",
        "/analytics/equipment",
    }


def test_browser_docs_are_disabled(client: TestClient) -> None:
    docs = client.get("/docs")
    redoc = client.get("/redoc")

    assert docs.status_code == 404
    assert redoc.status_code == 404
    assert "jsdelivr" not in docs.text
    assert "jsdelivr" not in redoc.text
