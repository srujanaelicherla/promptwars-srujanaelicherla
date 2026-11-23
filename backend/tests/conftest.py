"""Shared API test fixtures.

Non-emulator tests always run with memory persistence and without a Firestore
emulator host, even if the process inherited leftover Phase 8/9 environment.
Emulator tests skip when the emulator is not actually reachable.
"""

from __future__ import annotations

import os
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SAVED_FIRESTORE_EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")

STUDENT = {"Authorization": "Bearer test:user-student-physics"}
STUDENT_B = {"Authorization": "Bearer test:user-student-engineering"}
FACULTY = {"Authorization": "Bearer test:user-faculty-physics"}
FACULTY_ENG = {"Authorization": "Bearer test:user-faculty-engineering"}
FACULTY_CHEM = {"Authorization": "Bearer test:user-faculty-chemistry"}
ADMIN = {"Authorization": "Bearer test:user-admin"}


def firestore_emulator_available() -> bool:
    host = SAVED_FIRESTORE_EMULATOR_HOST
    if not host:
        return False
    url = host if "://" in host else f"http://{host}"
    try:
        urlopen(url, timeout=1.0)
        return True
    except (URLError, OSError, TimeoutError):
        return False


@pytest.fixture(autouse=True)
def isolate_persistence_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("firestore_emulator"):
        if not firestore_emulator_available():
            pytest.skip("Firestore emulator is not running; transaction safety is UNVERIFIED.")
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", SAVED_FIRESTORE_EMULATOR_HOST or "")
        monkeypatch.setenv("LABLINK_PERSISTENCE", "firestore")
        monkeypatch.setenv("LABLINK_AUTH_MODE", "test")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-lablink")
        return
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("LABLINK_PERSISTENCE", "memory")
    monkeypatch.setenv("LABLINK_AUTH_MODE", "test")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("LABLINK_AUTH_MODE", "test")
    monkeypatch.setenv("LABLINK_PERSISTENCE", "memory")
    monkeypatch.delenv("LABLINK_SERVICE_NAME", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    return TestClient(create_app())
