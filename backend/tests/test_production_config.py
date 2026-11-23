"""Production settings fail closed. No test-auth or memory fallback."""

import pytest

from app.config import load_settings
from app.main import create_app


def test_production_rejects_test_auth_and_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABLINK_ENV", "production")
    monkeypatch.setenv("LABLINK_AUTH_MODE", "test")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "memory")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-lablink")
    monkeypatch.setenv("LABLINK_CORS_ORIGINS", "https://example.invalid")
    with pytest.raises(ValueError, match="firebase"):
        load_settings()


def test_production_rejects_star_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABLINK_ENV", "production")
    monkeypatch.setenv("LABLINK_AUTH_MODE", "firebase")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-lablink")
    monkeypatch.setenv("LABLINK_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="CORS"):
        load_settings()


def test_production_requires_firestore_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABLINK_ENV", "production")
    monkeypatch.setenv("LABLINK_AUTH_MODE", "firebase")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-lablink")
    monkeypatch.setenv("LABLINK_CORS_ORIGINS", "https://example.invalid")
    monkeypatch.setattr("app.main.init_firebase", lambda _settings: False)
    with pytest.raises(RuntimeError, match="Firebase"):
        create_app()
