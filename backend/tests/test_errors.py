"""Error responses stay generic and do not echo request data."""

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.main import create_app


def test_unknown_route(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": "not_found",
        "message": "The requested resource does not exist.",
    }
    assert "traceback" not in response.text.lower()


def test_health_rejects_unsupported_method(client: TestClient) -> None:
    response = client.post("/health")

    assert response.status_code == 405
    assert response.json() == {
        "error": "method_not_allowed",
        "message": "This method is not allowed for the requested resource.",
    }
    assert response.headers["allow"] == "GET"


def test_validation_error_does_not_echo_values() -> None:
    app = create_app()

    class Sample(BaseModel):
        model_config = ConfigDict(extra="forbid")

        count: int

    @app.post("/samples")
    def create_sample(sample: Sample) -> Sample:
        return sample

    response = TestClient(app).post(
        "/samples",
        json={"count": "super-secret-value", "token": "also-secret"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["message"] == "The request is invalid."
    assert "count" in body["fields"]
    assert "super-secret-value" not in response.text
    assert "also-secret" not in response.text


def test_internal_error_hides_exception_text() -> None:
    app = create_app()

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("internal-detail-marker")

    response = TestClient(app, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "The request could not be completed.",
    }
    assert "internal-detail-marker" not in response.text
    assert "Traceback" not in response.text


def test_oversized_body_is_rejected(client: TestClient) -> None:
    payload = b"q" * 16_385
    response = client.post("/health", content=payload)

    assert response.status_code == 413
    assert payload not in response.content
    assert "traceback" not in response.text.lower()
