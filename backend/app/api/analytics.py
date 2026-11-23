"""Read-only analytics. Faculty is department-scoped; students are not callers."""

from datetime import datetime

from fastapi import APIRouter, Query, Request

from app.access import AccessStore
from app.analytics import build_departments, build_equipment, build_overview, parse_window
from app.authn import require_user
from app.bookings import BookingError, BookingStore
from app.models import Role
from app.schemas import AnalyticsOverview, DepartmentAnalyticsResponse, EquipmentAnalyticsResponse
from app.seed import read_catalog
from app.waitlist import WaitlistStore

router = APIRouter()


def _bookings(request: Request) -> BookingStore:
    store = getattr(request.app.state, "bookings", None)
    if not isinstance(store, BookingStore):
        raise RuntimeError("Application booking store is not configured")
    return store


def _access(request: Request) -> AccessStore:
    store = getattr(request.app.state, "access", None)
    if not isinstance(store, AccessStore):
        raise RuntimeError("Application access store is not configured")
    return store


def _waitlist(request: Request) -> WaitlistStore:
    store = getattr(request.app.state, "waitlist", None)
    if not isinstance(store, WaitlistStore):
        raise RuntimeError("Application waitlist store is not configured")
    return store


def _scope_department(actor) -> str | None:
    if actor.role is Role.ADMIN:
        return None
    return actor.department_id


def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    return parse_window(start, end)


@router.get("/analytics/overview", response_model=AnalyticsOverview)
def get_overview(
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> AnalyticsOverview:
    actor = require_user(request)
    window_start, window_end = _window(start, end)
    try:
        catalog = read_catalog(request.app.state)
        return build_overview(
            catalog=catalog,
            bookings=_bookings(request).snapshot(),
            requests=_access(request).snapshot(),
            approvals=_access(request).approvals_snapshot(),
            waitlist=_waitlist(request).snapshot(),
            window_start=window_start,
            window_end=window_end,
            department_id=_scope_department(actor),
        )
    except BookingError:
        raise
    except Exception as exc:
        raise BookingError(503, "unavailable", "Analytics could not be loaded.") from exc


@router.get("/analytics/departments", response_model=DepartmentAnalyticsResponse)
def get_departments(
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> DepartmentAnalyticsResponse:
    actor = require_user(request)
    window_start, window_end = _window(start, end)
    try:
        return build_departments(
            catalog=read_catalog(request.app.state),
            bookings=_bookings(request).snapshot(),
            requests=_access(request).snapshot(),
            waitlist=_waitlist(request).snapshot(),
            window_start=window_start,
            window_end=window_end,
            department_id=_scope_department(actor),
        )
    except BookingError:
        raise
    except Exception as exc:
        raise BookingError(503, "unavailable", "Analytics could not be loaded.") from exc


@router.get("/analytics/equipment", response_model=EquipmentAnalyticsResponse)
def get_equipment_analytics(
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> EquipmentAnalyticsResponse:
    actor = require_user(request)
    window_start, window_end = _window(start, end)
    try:
        return build_equipment(
            catalog=read_catalog(request.app.state),
            bookings=_bookings(request).snapshot(),
            requests=_access(request).snapshot(),
            waitlist=_waitlist(request).snapshot(),
            window_start=window_start,
            window_end=window_end,
            department_id=_scope_department(actor),
        )
    except BookingError:
        raise
    except Exception as exc:
        raise BookingError(503, "unavailable", "Analytics could not be loaded.") from exc
