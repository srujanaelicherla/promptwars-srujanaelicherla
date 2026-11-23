"""CORS: Authorization preflight is allowed; * and unknown origins are not."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_authorization_preflight_from_vite(client: TestClient) -> None:
    response = client.options(
        "/bookings",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,accept",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    allowed = response.headers["access-control-allow-headers"].casefold()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "*" not in response.headers.get("access-control-allow-origin", "")


def test_unknown_origin_is_rejected(client: TestClient) -> None:
    response = client.options(
        "/equipment",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_star_origin_env_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("LABLINK_CORS_ORIGINS", "*")
    app = create_app()
    client = TestClient(app)
    starred = client.options(
        "/equipment",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert starred.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-origin" not in starred.headers
    local = client.options(
        "/equipment",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert local.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_configured_origins_do_not_keep_localhost(monkeypatch) -> None:
    monkeypatch.setenv("LABLINK_CORS_ORIGINS", "https://lablink.example")
    client = TestClient(create_app())
    allowed = client.options(
        "/health",
        headers={
            "Origin": "https://lablink.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    local = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "https://lablink.example"
    assert "access-control-allow-origin" not in local.headers
