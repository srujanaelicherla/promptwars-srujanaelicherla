"""Scheduling recommendations, waitlist, and authenticated promotion."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.access import AccessStore
from app.authn import require_faculty_scope, require_roles, require_user
from app.bookings import BookingStore, lookup_equipment
from app.models import RecordId, ResourceKind, Role
from app.schemas import (
    OfferView,
    PromoteBody,
    PromoteResponse,
    SchedulingRequest,
    SchedulingResponse,
    WaitlistJoinBody,
    WaitlistListResponse,
    WaitlistView,
    BookingView,
)
from app.scheduling import recommend
from app.seed import read_catalog
from app.waitlist import (
    WaitlistStore,
    accept_offer,
    cancel_entry,
    expire_offers,
    join_waitlist,
    promote,
    rank_waitlist,
)

router = APIRouter()


def _bookings(request: Request) -> BookingStore:
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


def _offer_view(offer) -> OfferView:
    return OfferView(
        id=offer.id,
        waitlist_id=offer.waitlist_id,
        equipment_id=offer.equipment_id,
        project_id=offer.project_id,
        start=offer.start,
        end=offer.end,
        expires_at=offer.expires_at,
        status=offer.status,
        demo=True,
        note="Time-limited offer hold. Not a confirmed booking. Promotion is not a deployed job.",
    )


def _entry_view(entry, *, rank=None, eligible=None, feasible=None, provisional=None, explanation=None) -> WaitlistView:
    return WaitlistView(
        id=entry.id,
        equipment_id=entry.equipment_id,
        project_id=entry.project_id,
        duration_minutes=entry.duration_minutes,
        preferred_start=entry.preferred_start,
        preferred_end=entry.preferred_end,
        flexibility_minutes=entry.flexibility_minutes,
        status=entry.status,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        offer_id=entry.offer_id,
        offered_start=entry.offered_start,
        offered_end=entry.offered_end,
        offer_expires_at=entry.offer_expires_at,
        rank=rank,
        eligible=eligible,
        feasible=feasible,
        provisional=provisional,
        explanation=explanation,
        demo=True,
    )


@router.post("/scheduling/recommendations", response_model=SchedulingResponse)
def post_recommendations(request: Request, body: SchedulingRequest) -> SchedulingResponse:
    require_user(request)
    now = datetime.now(timezone.utc)
    expire_offers(waitlist=_waitlist(request), bookings=_bookings(request), now=now)
    return recommend(
        catalog=read_catalog(request.app.state),
        bookings=_bookings(request).snapshot(),
        offers=_waitlist(request).offers_snapshot(),
        equipment_id=body.equipment_id,
        project_id=body.project_id,
        duration_minutes=body.duration_minutes,
        preferred_start=body.preferred_start,
        preferred_end=body.preferred_end,
        flexibility_minutes=body.flexibility_minutes,
        increment_minutes=body.increment_minutes,
        now=now,
    )


@router.post("/scheduling/promote", response_model=PromoteResponse)
def post_promote(request: Request, body: PromoteBody) -> PromoteResponse:
    actor = require_user(request)
    require_roles(actor, Role.FACULTY, Role.ADMIN)
    catalog = read_catalog(request.app.state)
    equipment = lookup_equipment(catalog, body.equipment_id)
    require_faculty_scope(actor, equipment.department_id)
    now = datetime.now(timezone.utc)
    offer, existed = promote(
        catalog=catalog,
        bookings=_bookings(request),
        waitlist=_waitlist(request),
        access=_access(request),
        equipment_id=body.equipment_id,
        actor=actor,
        now=now,
    )
    if offer is None:
        return PromoteResponse(
            offer=None,
            promoted=False,
            idempotent=False,
            job="not_deployed",
            message="No eligible waitlist candidate could be offered. This is not a deployed job.",
            demo=True,
        )
    return PromoteResponse(
        offer=_offer_view(offer),
        promoted=not existed,
        idempotent=existed,
        job="not_deployed",
        message="Promotion is an authenticated idempotent operation, not a deployed cron job.",
        demo=True,
    )


@router.post("/waitlist", response_model=WaitlistView, status_code=201)
def post_waitlist(request: Request, body: WaitlistJoinBody) -> WaitlistView:
    actor = require_user(request)
    now = datetime.now(timezone.utc)
    entry = join_waitlist(
        catalog=read_catalog(request.app.state),
        bookings=_bookings(request),
        waitlist=_waitlist(request),
        actor=actor,
        equipment_id=body.equipment_id,
        project_id=body.project_id,
        duration_minutes=body.duration_minutes,
        preferred_start=body.preferred_start,
        preferred_end=body.preferred_end,
        flexibility_minutes=body.flexibility_minutes,
        now=now,
    )
    return _entry_view(entry)


@router.get("/waitlist", response_model=WaitlistListResponse)
def get_waitlist(request: Request) -> WaitlistListResponse:
    actor = require_user(request)
    now = datetime.now(timezone.utc)
    expire_offers(waitlist=_waitlist(request), bookings=_bookings(request), now=now)
    catalog = read_catalog(request.app.state)
    store = _waitlist(request)
    mine = store.for_user(actor.id)
    ranked_by_id = {}
    equipment_ids = {item.equipment_id for item in mine}
    all_entries = store.snapshot()
    bookings = _bookings(request).snapshot()
    for equipment_id in equipment_ids:
        rows = rank_waitlist(
            catalog=catalog,
            equipment_id=equipment_id,
            entries=[item for item in all_entries if item.equipment_id == equipment_id],
            bookings=bookings,
            now=now,
            viewer_is_faculty=False,
        )
        for row in rows:
            ranked_by_id[row.request_id] = row
    items = []
    for entry in mine:
        row = ranked_by_id.get(entry.id)
        items.append(
            _entry_view(
                entry,
                rank=row.rank if row else None,
                eligible=row.eligible if row else None,
                feasible=row.feasible if row else None,
                provisional=row.provisional if row else None,
                explanation=row.explanation if row else None,
            )
        )
    items.sort(key=lambda item: (item.created_at, item.id))
    return WaitlistListResponse(items=items, source="synthetic", demo=True)


@router.post("/waitlist/{entry_id}/cancel", response_model=WaitlistView)
def post_waitlist_cancel(request: Request, entry_id: RecordId) -> WaitlistView:
    actor = require_user(request)
    now = datetime.now(timezone.utc)
    entry = cancel_entry(
        waitlist=_waitlist(request),
        bookings=_bookings(request),
        actor=actor,
        entry_id=entry_id,
        now=now,
    )
    return _entry_view(entry)


@router.post("/waitlist/{entry_id}/accept", response_model=BookingView)
def post_waitlist_accept(request: Request, entry_id: RecordId) -> BookingView:
    actor = require_user(request)
    now = datetime.now(timezone.utc)
    booking = accept_offer(
        catalog=read_catalog(request.app.state),
        bookings=_bookings(request),
        waitlist=_waitlist(request),
        access=_access(request),
        actor=actor,
        entry_id=entry_id,
        now=now,
    )
    catalog = read_catalog(request.app.state)
    item = next((row for row in catalog.equipment if row.id == booking.equipment_id), None)
    return BookingView(
        id=booking.id,
        equipment_id=booking.equipment_id,
        equipment_name=item.name if item is not None else booking.equipment_id,
        kind=item.kind if item is not None else ResourceKind.EQUIPMENT,
        project_id=booking.project_id,
        purpose=booking.purpose,
        start=booking.start,
        end=booking.end,
        status=booking.status,
        user_id=booking.user_id,
        demo=True,
    )
