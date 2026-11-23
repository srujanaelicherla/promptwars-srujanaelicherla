"""Server-side identity. Browser requests use one local demo student."""

from __future__ import annotations

import logging
from typing import Protocol

from fastapi import Request

from app.bookings import BookingError
from app.config import read_settings
from app.models import Role, User
from app.users import UserStore

logger = logging.getLogger("lablink")

DEMO_USER_HEADER = "x-lablink-demo-user"
TEST_TOKEN_PREFIX = "test:"
DEMO_STUDENT_ID = "user-student-physics"
DEMO_STUDENT = User(id=DEMO_STUDENT_ID, role=Role.STUDENT, department_id="dept-physics")


class TokenVerifier(Protocol):
    def verify(self, token: str) -> dict[str, str]:
        """Return uid and optional email. Must not log the token."""


class FirebaseTokenVerifier:
    def verify(self, token: str) -> dict[str, str]:
        from firebase_admin import auth
        from firebase_admin.auth import (
            ExpiredIdTokenError,
            InvalidIdTokenError,
            RevokedIdTokenError,
            UserNotFoundError,
        )

        try:
            decoded = auth.verify_id_token(token, check_revoked=True)
        except ExpiredIdTokenError as exc:
            raise BookingError(401, "unauthorized", "The session has expired.") from exc
        except (InvalidIdTokenError, RevokedIdTokenError, UserNotFoundError) as exc:
            raise BookingError(401, "unauthorized", "The credential is invalid.") from exc
        except Exception as exc:
            logger.info("Token verification failed: %s", type(exc).__name__)
            raise BookingError(401, "unauthorized", "The credential is invalid.") from exc
        uid = decoded.get("uid")
        if not isinstance(uid, str) or uid.strip() == "":
            raise BookingError(401, "unauthorized", "The credential is invalid.")
        email = decoded.get("email")
        return {"uid": uid, "email": email if isinstance(email, str) else ""}


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise BookingError(401, "unauthorized", "The credential is malformed.")
    token = parts[1].strip()
    if token == "":
        raise BookingError(401, "unauthorized", "The credential is malformed.")
    return token


def demo_student(users: UserStore) -> User:
    found = users.get(DEMO_STUDENT_ID)
    return found if found is not None else DEMO_STUDENT


def _test_user(request: Request, users: UserStore) -> User:
    token = _bearer_token(request)
    if token is not None:
        if not token.startswith(TEST_TOKEN_PREFIX):
            raise BookingError(401, "unauthorized", "The credential is invalid.")
        user_id = token[len(TEST_TOKEN_PREFIX) :].strip()
        user = users.get(user_id)
        if user is None:
            raise BookingError(401, "unauthorized", "Unknown test identity.")
        return user
    raw = request.headers.get(DEMO_USER_HEADER)
    if raw is not None and raw.strip() != "":
        user = users.get(raw.strip())
        if user is None:
            raise BookingError(401, "unauthorized", "Unknown test identity.")
        return user
    return demo_student(users)


def verified_account_id(request: Request) -> str:
    """Return the verified account id without requiring a LabLink profile."""

    settings = read_settings(request.app.state)
    if settings.auth_mode != "test":
        return DEMO_STUDENT_ID
    token = _bearer_token(request)
    if token is None:
        return DEMO_STUDENT_ID
    if not token.startswith(TEST_TOKEN_PREFIX):
        raise BookingError(401, "unauthorized", "The credential is invalid.")
    user_id = token[len(TEST_TOKEN_PREFIX) :].strip()
    if user_id == "":
        raise BookingError(401, "unauthorized", "The credential is malformed.")
    return user_id


def require_user(request: Request) -> User:
    settings = read_settings(request.app.state)
    users = read_users(request.app.state)
    if settings.auth_mode == "test":
        return _test_user(request, users)
    return demo_student(users)


def require_roles(user: User, *roles: Role) -> None:
    if user.role not in roles:
        raise BookingError(403, "forbidden", "This identity cannot perform that action.")


def require_faculty_scope(actor: User, department_id: str) -> None:
    if actor.role is Role.ADMIN:
        return
    if actor.role is Role.FACULTY and actor.department_id == department_id:
        return
    raise BookingError(
        403,
        "forbidden",
        "This identity is outside the authorized department scope.",
    )


def read_users(state: object) -> UserStore:
    store = getattr(state, "users", None)
    if not isinstance(store, UserStore):
        raise RuntimeError("Application user store is not configured")
    return store
