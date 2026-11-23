"""Firebase Admin initialization. Never expose credentials to the frontend."""

from __future__ import annotations

import logging
import os

from app.config import Settings

logger = logging.getLogger("lablink")

_READY = False


def firebase_configured(settings: Settings) -> bool:
    if os.environ.get("FIRESTORE_EMULATOR_HOST") or os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        return True
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    return settings.firebase_project_id is not None and settings.persistence == "firestore"


def init_firebase(settings: Settings) -> bool:
    """Initialize Admin SDK. Returns False when credentials are absent."""

    global _READY
    if _READY:
        return True
    if settings.auth_mode == "test" and settings.persistence != "firestore":
        return False
    if not firebase_configured(settings):
        logger.info("Firebase Admin is not configured; protected firebase routes stay closed.")
        return False
    import firebase_admin

    if firebase_admin._apps:
        _READY = True
        return True
    project_id = settings.firebase_project_id or os.environ.get("GCLOUD_PROJECT") or "demo-lablink"
    try:
        firebase_admin.initialize_app(options={"projectId": project_id})
    except Exception as exc:
        logger.info("Firebase Admin initialization failed: %s", type(exc).__name__)
        return False
    _READY = True
    return True
