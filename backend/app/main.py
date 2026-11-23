"""Application entry point.

Run from the backend directory:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("lablink")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.access import AccessStore
from app.ai_service import new_cache
from app.api.access import router as access_router
from app.api.analytics import router as analytics_router
from app.api.account import router as account_router
from app.api.ai import router as ai_router
from app.api.bookings import router as bookings_router
from app.api.scheduling import router as scheduling_router
from app.api.equipment import router as equipment_router
from app.api.matches import router as matches_router
from app.api.router import router
from app.gemini import GeminiClient, api_key_from_env, load_gemini_key_from_file
from app.rag import HashEmbedder, build_index
from app.rate_limit import RateLimiter
from app.bookings import BookingStore
from app.config import Settings, load_settings
from app.errors import register_error_handlers
from app.firebase_app import init_firebase
from app.security import guard_requests
from app.seed import load_seed
from app.users import UserStore
from app.waitlist import WaitlistStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API. Pass settings only from tests."""

    resolved = load_settings() if settings is None else settings
    application = FastAPI(
        title="LabLink API",
        summary="Health, discovery, matching, bookings, faculty approvals, Gemini assistant, scheduling, and analytics.",
        version="0.1.0",
        debug=False,
        docs_url=None,
        redoc_url=None,
        max_body_size=16_384,
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
    )
    catalog = load_seed()
    firebase_ready = False
    production = os.environ.get("LABLINK_ENV", "").strip().casefold() == "production"
    if resolved.auth_mode == "firebase" or resolved.persistence == "firestore":
        firebase_ready = init_firebase(resolved)
        if production:
            if resolved.persistence != "firestore" or not firebase_ready:
                raise RuntimeError("Production requires Firestore and Firebase Admin")
        if resolved.persistence == "firestore" and not firebase_ready:
            raise RuntimeError("Firestore persistence requires Firebase Admin")
        if firebase_ready and resolved.persistence == "firestore":
            from google.cloud import firestore

            from app.firestore_store import (
                FirestoreAccessStore,
                FirestoreBookingStore,
                FirestoreUserStore,
                FirestoreWaitlistStore,
                load_catalog,
            )

            client = firestore.Client(project=resolved.firebase_project_id or "demo-lablink")
            loaded = load_catalog(client)
            if loaded.departments:
                catalog = loaded
            application.state.users = FirestoreUserStore(client)
            application.state.bookings = FirestoreBookingStore(client)
            application.state.access = FirestoreAccessStore(client, application.state.bookings)
            application.state.waitlist = FirestoreWaitlistStore(client)
        else:
            application.state.users = UserStore(catalog.users)
            application.state.bookings = BookingStore(catalog.bookings)
            application.state.access = AccessStore(
                catalog.access_requests,
                catalog.approvals,
                catalog.allocation_decisions,
            )
            application.state.waitlist = WaitlistStore()
    else:
        application.state.users = UserStore(catalog.users)
        application.state.bookings = BookingStore(catalog.bookings)
        application.state.access = AccessStore(
            catalog.access_requests,
            catalog.approvals,
            catalog.allocation_decisions,
        )
        application.state.waitlist = WaitlistStore()

    application.state.settings = resolved
    application.state.catalog = catalog
    application.state.firebase_ready = firebase_ready
    application.state.token_verifier = None
    if "pytest" not in sys.modules:
        load_gemini_key_from_file(Path(__file__).resolve().parent.parent / ".env")
    api_key = api_key_from_env()
    ai_client: GeminiClient | None = None
    embedder: HashEmbedder | GeminiClient
    if api_key:
        try:
            ai_client = GeminiClient(api_key)
            embedder = ai_client
        except Exception as exc:
            logger.info("Gemini client init failed: %s", type(exc).__name__)
            ai_client = None
            embedder = HashEmbedder()
    else:
        embedder = HashEmbedder()
    try:
        index = build_index(embedder)
    except Exception as exc:
        logger.info("AI index build failed: %s", type(exc).__name__)
        ai_client = None
        index = build_index(HashEmbedder())
    application.state.ai_client = ai_client
    application.state.ai_index = index
    application.state.ai_cache = new_cache()
    application.state.ai_limiter = RateLimiter()
    register_error_handlers(application)
    application.middleware("http")(guard_requests)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-LabLink-Demo-User"],
    )
    application.include_router(router)
    application.include_router(equipment_router)
    application.include_router(matches_router)
    application.include_router(bookings_router)
    application.include_router(access_router)
    application.include_router(account_router)
    application.include_router(ai_router)
    application.include_router(scheduling_router)
    application.include_router(analytics_router)
    return application


app = create_app()
