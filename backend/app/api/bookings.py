"""Booking and availability routes. Identity comes from verified auth, not the client."""

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.access import AccessStore
from app.authn import require_roles, require_user
from app.bookings import (
    BookingStore,
    availability_window,
    lookup_equipment,
    resolve_project_id,
    subtract_busy,
    to_booking_view,
)
from app.models import RecordId, Role
from app.schemas import (
    AvailabilityResponse,
    BookingCreate,
    BookingListResponse,
    BookingView,
    TimeInterval,
)
from app.scheduling import combined_busy
from app.seed import read_catalog
from app.waitlist import WaitlistStore, promote

router = APIRouter()


def _store(request: Request) -> BookingStore:
    store = getattr(request.app.state, "bookings", None)
    if not isinstance(store, BookingStore):
        raise RuntimeError("Application booking store is not configured")
    return store


def _waitlist(request: Request) -> WaitlistStore:
    store = getattr(request.app.state, "waitlist", None)
    if not isinstance(store, WaitlistStore):
        raise RuntimeError("Application waitlist store is not configured")
    return store


def _access(request: Request) -> AccessStore:
    store = getattr(request.app.state, "access", None)
    if not isinstance(store, AccessStore):
        raise RuntimeError("Application access store is not configured")
    return store


@router.get("/equipment/{equipment_id}/availability", response_model=AvailabilityResponse)
def read_availability(
    request: Request,
    equipment_id: RecordId,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AvailabilityResponse:
    require_user(request)
    catalog = read_catalog(request.app.state)
    lookup_equipment(catalog, equipment_id)
    window_start, window_end = availability_window(on_date=on_date, start=start, end=end)
    now = datetime.now(timezone.utc)
    busy = combined_busy(
        _store(request).snapshot(),
        _waitlist(request).offers_snapshot(),
        equipment_id,
        now=now,
    )
    unavailable = [
        TimeInterval(start=max(item[0], window_start), end=min(item[1], window_end))
        for item in busy
        if item[0] < window_end and item[1] > window_start
    ]
    available = [
        TimeInterval(start=gap[0], end=gap[1])
        for gap in subtract_busy(window_start, window_end, busy)
    ]
    return AvailabilityResponse(
        equipment_id=equipment_id,
        start=window_start,
        end=window_end,
        available=available,
        unavailable=unavailable,
        source="synthetic",
        demo=True,
    )


@router.post("/bookings", response_model=BookingView, status_code=201)
def create_booking(request: Request, body: BookingCreate) -> BookingView:
    actor = require_user(request)
    require_roles(actor, Role.STUDENT, Role.ADMIN)
    catalog = read_catalog(request.app.state)
    equipment = lookup_equipment(catalog, body.equipment_id)
    booking = _store(request).create(
        catalog=catalog,
        equipment_id=body.equipment_id,
        project_id=resolve_project_id(catalog, equipment, body.project_id),
        start=body.start,
        end=body.end,
        now=datetime.now(timezone.utc),
        user_id=actor.id,
        purpose=body.purpose,
    )
    return to_booking_view(booking, catalog)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingView)
def cancel_booking(request: Request, booking_id: RecordId) -> BookingView:
    actor = require_user(request)
    store = _store(request)
    booking = store.cancel(booking_id=booking_id, actor=actor)
    now = datetime.now(timezone.utc)
    promote(
        catalog=read_catalog(request.app.state),
        bookings=store,
        waitlist=_waitlist(request),
        access=_access(request),
        equipment_id=booking.equipment_id,
        actor=actor,
        now=now,
    )
    return to_booking_view(booking, read_catalog(request.app.state))


@router.get("/bookings", response_model=BookingListResponse)
def list_bookings(request: Request) -> BookingListResponse:
    actor = require_user(request)
    items = _store(request).for_user(actor.id)
    items.sort(key=lambda item: (item.start, item.id))
    return BookingListResponse(
        items=[to_booking_view(item, read_catalog(request.app.state)) for item in items],
        demo_user_id=actor.id,
        source="synthetic",
        demo=True,
    )
