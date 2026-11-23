"""Access-request and conflict routes. Authorization is enforced server-side."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.access import AccessStore, listed_for
from app.authn import read_users, require_faculty_scope, require_roles, require_user
from app.bookings import BookingStore, lookup_equipment, resolve_project_id
from app.conflicts import WEIGHTS, evaluate_conflicts
from app.models import AccessRequest, Approval, ApprovalDecision, Role
from app.schemas import (
    AccessDecisionBody,
    AccessRequestCreate,
    AccessRequestListResponse,
    AccessRequestView,
    ApprovalView,
    ConflictItem,
    ConflictListResponse,
)
from app.seed import read_catalog

router = APIRouter()


def _access(request: Request) -> AccessStore:
    store = getattr(request.app.state, "access", None)
    if not isinstance(store, AccessStore):
        raise RuntimeError("Application access store is not configured")
    return store


def _bookings(request: Request) -> BookingStore:
    store = getattr(request.app.state, "bookings", None)
    if not isinstance(store, BookingStore):
        raise RuntimeError("Application booking store is not configured")
    return store


def _live_catalog(request: Request):
    catalog = read_catalog(request.app.state)
    return catalog.model_copy(update={"users": read_users(request.app.state).snapshot()})


def _approval_view(item: Approval) -> ApprovalView:
    return ApprovalView(
        id=item.id,
        request_id=item.request_id,
        faculty_id=item.faculty_id,
        decision=item.decision,
        comments=item.comments,
        decided_at=item.decided_at,
        demo=True,
    )


def _request_view(item: AccessRequest, approvals: list[Approval], *, hide_user: bool) -> AccessRequestView:
    return AccessRequestView(
        id=item.id,
        equipment_id=item.equipment_id,
        project_id=item.project_id,
        status=item.status,
        justification=item.justification,
        created_at=item.created_at,
        start=item.start,
        end=item.end,
        user_id=None if hide_user else item.user_id,
        approvals=[_approval_view(row) for row in approvals],
        demo=True,
    )


@router.post("/access-requests", response_model=AccessRequestView, status_code=201)
def create_access_request(request: Request, body: AccessRequestCreate) -> AccessRequestView:
    catalog = _live_catalog(request)
    actor = require_user(request)
    equipment = lookup_equipment(catalog, body.equipment_id)
    item = _access(request).submit(
        catalog=catalog,
        actor=actor,
        equipment_id=body.equipment_id,
        project_id=resolve_project_id(catalog, equipment, body.project_id),
        justification=body.justification,
        start=body.start,
        end=body.end,
        now=datetime.now(timezone.utc),
    )
    return _request_view(item, [], hide_user=False)


@router.get("/access-requests", response_model=AccessRequestListResponse)
def list_access_requests(request: Request) -> AccessRequestListResponse:
    catalog = _live_catalog(request)
    actor = require_user(request)
    store = _access(request)
    departments = {item.id: item.department_id for item in catalog.equipment}
    items = listed_for(actor, store.snapshot(), equipment_departments=departments)
    privileged = actor.role in {Role.FACULTY, Role.ADMIN}
    views = [
        _request_view(
            item,
            store.approvals_for(item.id),
            hide_user=not privileged and item.user_id != actor.id,
        )
        for item in items
    ]
    return AccessRequestListResponse(
        items=views,
        demo_user_id=actor.id,
        demo_role=actor.role.value,
        source="synthetic",
        demo=True,
    )


@router.post("/access-requests/{request_id}/approve", response_model=AccessRequestView)
def approve_access_request(
    request: Request,
    request_id: str,
    body: AccessDecisionBody,
) -> AccessRequestView:
    return _decide(request, request_id, ApprovalDecision.APPROVED, body.comments)


@router.post("/access-requests/{request_id}/reject", response_model=AccessRequestView)
def reject_access_request(
    request: Request,
    request_id: str,
    body: AccessDecisionBody,
) -> AccessRequestView:
    return _decide(request, request_id, ApprovalDecision.REJECTED, body.comments)


def _decide(
    request: Request,
    request_id: str,
    decision: ApprovalDecision,
    comments: str,
) -> AccessRequestView:
    catalog = _live_catalog(request)
    actor = require_user(request)
    updated, approval, booking_id = _access(request).decide(
        catalog=catalog,
        bookings=_bookings(request),
        actor=actor,
        request_id=request_id,
        decision=decision,
        comments=comments,
        now=datetime.now(timezone.utc),
    )
    view = _request_view(updated, [approval], hide_user=False)
    return view.model_copy(update={"booking_id": booking_id})


@router.get("/equipment/{equipment_id}/conflicts", response_model=ConflictListResponse)
def list_conflicts(request: Request, equipment_id: str) -> ConflictListResponse:
    catalog = _live_catalog(request)
    actor = require_user(request)
    require_roles(actor, Role.FACULTY, Role.ADMIN)
    equipment = lookup_equipment(catalog, equipment_id)
    require_faculty_scope(actor, equipment.department_id)
    rows = evaluate_conflicts(
        catalog=catalog,
        equipment=equipment,
        requests=_access(request).snapshot(),
        bookings=_bookings(request).snapshot(),
        now=datetime.now(timezone.utc),
        viewer_is_faculty=True,
    )
    return ConflictListResponse(
        equipment_id=equipment.id,
        items=[
            ConflictItem(
                request_id=row.request_id,
                project_id=row.project_id,
                requester_department_id=row.requester_department_id,
                requester_user_id=row.requester_user_id,
                eligible=row.eligible,
                feasible=row.feasible,
                provisional=row.provisional,
                score=row.score,
                rank=row.rank or 0,
                components=row.components,
                missing_inputs=list(row.missing_inputs),
                explanation=row.explanation,
                alternatives=list(row.alternatives),
            )
            for row in rows
        ],
        weights=dict(WEIGHTS),
        source="synthetic",
        demo=True,
        note="Faculty view. Scores use catalog data only and are not live allocation.",
    )
