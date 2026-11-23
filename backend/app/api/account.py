"""Authenticated profile, student bootstrap, and admin role provisioning."""

import logging

from fastapi import APIRouter, Request, Response

from app.authn import read_users, require_roles, require_user, verified_account_id
from app.bookings import BookingError
from app.config import read_settings
from app.models import Role, User
from app.schemas import BootstrapBody, MeResponse, RoleUpdateBody
from app.seed import read_catalog

logger = logging.getLogger("lablink")

router = APIRouter()


@router.get("/me", response_model=MeResponse)
def read_me(request: Request) -> MeResponse:
    actor = require_user(request)
    settings = read_settings(request.app.state)
    return MeResponse(
        id=actor.id,
        role=actor.role,
        department_id=actor.department_id,
        auth=settings.auth_mode,
        demo=True,
    )


@router.post("/users/bootstrap", response_model=MeResponse)
def bootstrap_user(request: Request, response: Response, body: BootstrapBody) -> MeResponse:
    """Create a student profile for a verified account. Idempotent. Role cannot be chosen."""

    settings = read_settings(request.app.state)
    catalog = read_catalog(request.app.state)
    if body.department_id not in {item.id for item in catalog.departments}:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    uid = verified_account_id(request)
    users = read_users(request.app.state)
    existing = users.get(uid)
    if existing is not None:
        response.status_code = 200
        return MeResponse(
            id=existing.id,
            role=existing.role,
            department_id=existing.department_id,
            auth=settings.auth_mode,
            demo=True,
        )
    user = User(id=uid, role=Role.STUDENT, department_id=body.department_id)
    users.upsert(user)
    response.status_code = 201
    return MeResponse(
        id=user.id,
        role=user.role,
        department_id=user.department_id,
        auth=settings.auth_mode,
        demo=True,
    )


@router.post("/admin/users/{user_id}/role", response_model=MeResponse)
def assign_role(request: Request, user_id: str, body: RoleUpdateBody) -> MeResponse:
    """Trusted admin-only elevation. There is no public self-service for faculty/admin."""

    actor = require_user(request)
    require_roles(actor, Role.ADMIN)
    catalog = read_catalog(request.app.state)
    if body.department_id not in {item.id for item in catalog.departments}:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    users = read_users(request.app.state)
    target = users.get(user_id)
    if target is None:
        raise BookingError(404, "not_found", "The requested resource does not exist.")
    updated = User(id=target.id, role=body.role, department_id=body.department_id)
    users.upsert(updated)
    if getattr(request.app.state, "firebase_ready", False):
        try:
            from firebase_admin import auth

            auth.set_custom_user_claims(
                user_id,
                {"role": updated.role.value, "department_id": updated.department_id},
            )
        except Exception as exc:
            logger.info("Custom claims update failed: %s", type(exc).__name__)
    settings = read_settings(request.app.state)
    return MeResponse(
        id=updated.id,
        role=updated.role,
        department_id=updated.department_id,
        auth=settings.auth_mode,
        demo=True,
    )
