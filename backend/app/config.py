"""Non-secret application settings.

Secrets never enter Settings. Firebase Admin reads ADC or the emulator from
the process environment separately. Client-supplied roles are ignored.
"""

import os
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_SERVICE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DEFAULT_SERVICE_NAME = "lablink-api"
AuthMode = Literal["test", "firebase"]
Persistence = Literal["memory", "firestore"]


class Settings(BaseModel):
    """Public service identity and auth/persistence mode. Holds no credentials."""

    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(default=_DEFAULT_SERVICE_NAME, min_length=1, max_length=64)
    auth_mode: AuthMode = "firebase"
    persistence: Persistence = "memory"
    firebase_project_id: str | None = None
    cors_origins: tuple[str, ...] = ()


def _auth_mode() -> AuthMode:
    raw = os.environ.get("LABLINK_AUTH_MODE", "").strip().casefold()
    if raw == "test":
        return "test"
    if raw == "firebase":
        return "firebase"
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "test"
    return "firebase"


def _persistence(auth_mode: AuthMode) -> Persistence:
    raw = os.environ.get("LABLINK_PERSISTENCE", "").strip().casefold()
    if raw == "firestore":
        return "firestore"
    if raw == "memory":
        return "memory"
    if auth_mode == "test":
        return "memory"
    if os.environ.get("FIRESTORE_EMULATOR_HOST") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return "firestore"
    return "memory"


def _cors_origins() -> tuple[str, ...]:
    """Local Vite origins only when LABLINK_CORS_ORIGINS is unset. * is never allowed."""

    extra = os.environ.get("LABLINK_CORS_ORIGINS", "")
    added: list[str] = []
    for item in extra.split(","):
        origin = item.strip()
        if origin == "*" or origin == "":
            continue
        if origin.startswith("http://") or origin.startswith("https://"):
            added.append(origin)
    if added:
        return tuple(dict.fromkeys(added))
    return (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )


def _is_production() -> bool:
    return os.environ.get("LABLINK_ENV", "").strip().casefold() == "production"


def load_settings() -> Settings:
    """Load public settings. Invalid service names fail closed without echoing the value."""

    raw = os.environ.get("LABLINK_SERVICE_NAME", _DEFAULT_SERVICE_NAME)
    if _SERVICE_NAME.fullmatch(raw) is None:
        raise ValueError("LABLINK_SERVICE_NAME must be a lowercase identifier")
    auth_mode = _auth_mode()
    persistence = _persistence(auth_mode)
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "").strip() or None
    cors_origins = _cors_origins()
    if _is_production():
        if auth_mode != "firebase":
            raise ValueError("Production requires LABLINK_AUTH_MODE=firebase")
        if persistence != "firestore":
            raise ValueError("Production requires LABLINK_PERSISTENCE=firestore")
        if not project_id:
            raise ValueError("Production requires FIREBASE_PROJECT_ID")
        extra = os.environ.get("LABLINK_CORS_ORIGINS", "").strip()
        if extra == "" or extra == "*":
            raise ValueError("Production requires LABLINK_CORS_ORIGINS with explicit https origins")
        if any(item == "*" for item in extra.split(",")):
            raise ValueError("Production CORS must not include *")
        if not cors_origins:
            raise ValueError("Production requires LABLINK_CORS_ORIGINS with explicit https origins")
    return Settings(
        service_name=raw,
        auth_mode=auth_mode,
        persistence=persistence,
        firebase_project_id=project_id,
        cors_origins=cors_origins,
    )


def read_settings(state: object) -> Settings:
    """Return settings stored on the application, or fail closed."""

    settings = getattr(state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured")
    return settings
