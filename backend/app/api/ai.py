"""AI endpoints. Authorization is the same as other authenticated routes."""

from fastapi import APIRouter, Request

from app.ai_service import answer_question, explain_equipment, extract_requirements
from app.authn import require_user
from app.bookings import BookingStore
from app.gemini import require_ai
from app.rate_limit import RateLimiter
from app.schemas import (
    AssistantQueryBody,
    AssistantQueryResponse,
    EquipmentExplanationBody,
    EquipmentExplanationResponse,
    ProjectRequirementsBody,
    ProjectRequirementsResponse,
)
from app.seed import read_catalog

router = APIRouter()


def _limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "ai_limiter", None)
    if not isinstance(limiter, RateLimiter):
        raise RuntimeError("AI rate limiter is not configured")
    return limiter


def _bookings(request: Request) -> BookingStore:
    store = getattr(request.app.state, "bookings", None)
    if not isinstance(store, BookingStore):
        raise RuntimeError("Application booking store is not configured")
    return store


@router.post("/ai/project-requirements", response_model=ProjectRequirementsResponse)
def post_project_requirements(request: Request, body: ProjectRequirementsBody) -> ProjectRequirementsResponse:
    actor = require_user(request)
    _limiter(request).check(actor.id)
    return extract_requirements(
        client=require_ai(request.app.state),
        catalog=read_catalog(request.app.state),
        description=body.description,
        cache=request.app.state.ai_cache,
    )


@router.post("/ai/assistant/query", response_model=AssistantQueryResponse)
def post_assistant_query(request: Request, body: AssistantQueryBody) -> AssistantQueryResponse:
    actor = require_user(request)
    _limiter(request).check(actor.id)
    return answer_question(
        client=require_ai(request.app.state),
        catalog=read_catalog(request.app.state),
        bookings=_bookings(request),
        index=request.app.state.ai_index,
        question=body.question,
        cache=request.app.state.ai_cache,
    )


@router.post("/ai/equipment-explanation", response_model=EquipmentExplanationResponse)
def post_equipment_explanation(
    request: Request,
    body: EquipmentExplanationBody,
) -> EquipmentExplanationResponse:
    actor = require_user(request)
    _limiter(request).check(actor.id)
    return explain_equipment(
        client=require_ai(request.app.state),
        catalog=read_catalog(request.app.state),
        index=request.app.state.ai_index,
        equipment_id=body.equipment_id,
        project_description=body.project_description,
        cache=request.app.state.ai_cache,
    )
