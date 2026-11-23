"""Response models for the LabLink API."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models import (
    ActorId,
    ApprovalDecision,
    BookingStatus,
    Equipment,
    OfferStatus,
    RecordId,
    RequestStatus,
    ResourceKind,
    Role,
    SpecComparison,
    Suitability,
    WaitlistStatus,
)

ErrorCode = Literal[
    "not_found",
    "method_not_allowed",
    "request_failed",
    "invalid_request",
    "internal_error",
    "conflict",
    "restricted",
    "unavailable",
    "unauthorized",
    "forbidden",
    "rate_limited",
]


class HealthResponse(BaseModel):
    """Public health payload. Contains no configuration beyond the service name."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: str = Field(min_length=1, max_length=64)


class ErrorResponse(BaseModel):
    """Client-facing error. Never includes exception text or submitted values."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorCode
    message: str = Field(min_length=1, max_length=200)
    fields: list[str] | None = None


class EquipmentListResponse(BaseModel):
    """Paginated catalog listing. Status is catalog state, not live availability."""

    model_config = ConfigDict(extra="forbid")

    items: list[Equipment]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
    source: Literal["synthetic"]


class EquipmentMatch(BaseModel):
    """One ranked catalog match. Score is not live availability."""

    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    name: str = Field(min_length=1, max_length=120)
    department_id: RecordId
    score: float = Field(ge=0, le=1)
    suitability: Suitability
    matched_requirements: list[str]
    unmet_requirements: list[str]
    explanation: str = Field(min_length=1, max_length=500)


class EquipmentMatchListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: RecordId
    items: list[EquipmentMatch]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    source: Literal["synthetic"]


class TimeInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime


class AvailabilityResponse(BaseModel):
    """Gaps computed from in-memory bookings. Not live multi-user availability."""

    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    start: datetime
    end: datetime
    available: list[TimeInterval]
    unavailable: list[TimeInterval]
    source: Literal["synthetic"]
    demo: Literal[True]


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    project_id: RecordId | None = None
    purpose: str = Field(default="", max_length=200)
    start: AwareDatetime
    end: AwareDatetime


class BookingView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RecordId
    equipment_id: RecordId
    equipment_name: str = Field(min_length=1, max_length=120)
    kind: ResourceKind = ResourceKind.EQUIPMENT
    project_id: RecordId
    purpose: str = Field(default="", max_length=200)
    start: datetime
    end: datetime
    status: BookingStatus
    user_id: ActorId
    demo: Literal[True]


class BookingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BookingView]
    demo_user_id: ActorId
    source: Literal["synthetic"]
    demo: Literal[True]


class AccessRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    project_id: RecordId | None = None
    justification: str = Field(min_length=1, max_length=1000)
    start: AwareDatetime
    end: AwareDatetime


class AccessDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comments: str = Field(min_length=1, max_length=500)


class ApprovalView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RecordId
    request_id: RecordId
    faculty_id: RecordId
    decision: ApprovalDecision
    comments: str
    decided_at: datetime
    demo: Literal[True]


class AccessRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RecordId
    equipment_id: RecordId
    project_id: RecordId
    status: RequestStatus
    justification: str
    created_at: datetime
    start: datetime | None
    end: datetime | None
    user_id: ActorId | None
    approvals: list[ApprovalView]
    booking_id: str | None = None
    demo: Literal[True]


class AccessRequestListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AccessRequestView]
    demo_user_id: ActorId
    demo_role: str
    source: Literal["synthetic"]
    demo: Literal[True]


class ConflictItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: RecordId
    project_id: RecordId
    requester_department_id: str
    requester_user_id: ActorId | None
    eligible: bool
    feasible: bool
    provisional: bool
    score: float | None
    rank: int
    components: dict[str, float | None]
    missing_inputs: list[str]
    explanation: str
    alternatives: list[str]


class ConflictListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    items: list[ConflictItem]
    weights: dict[str, float]
    source: Literal["synthetic"]
    demo: Literal[True]
    note: str


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ActorId
    role: Role
    department_id: RecordId
    auth: Literal["firebase", "test"]
    demo: Literal[True]


class BootstrapBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: RecordId


class RoleUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    department_id: RecordId


class ExtractedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    mandatory: bool = True
    comparison: SpecComparison = SpecComparison.EQUAL


class ProjectRequirementsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=8, max_length=4000)


class CitationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    section: str
    doc_id: str
    synthetic: Literal[True]


class ProjectRequirementsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    requirements: list[ExtractedRequirement] = Field(max_length=12)
    matches: list[EquipmentMatch]
    warnings: list[str]
    source: Literal["gemini"]
    demo: Literal[True]


class AssistantQueryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=4, max_length=2000)


class AssistantQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    citations: list[CitationView]
    equipment_ids: list[RecordId]
    evidence_insufficient: bool
    refused: bool
    source: Literal["gemini", "catalog", "refused"]
    demo: Literal[True]


class EquipmentExplanationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    project_description: str | None = Field(default=None, max_length=4000)


class EquipmentExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    answer: str = Field(min_length=1, max_length=4000)
    citations: list[CitationView]
    match: EquipmentMatch | None
    source: Literal["gemini"]
    demo: Literal[True]


class SchedulingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    project_id: RecordId
    duration_minutes: int = Field(ge=15, le=480)
    preferred_start: AwareDatetime
    preferred_end: AwareDatetime
    flexibility_minutes: int = Field(default=0, ge=0, le=1440)
    increment_minutes: int = Field(default=15, ge=15, le=60)


class RecommendedSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    start: datetime
    end: datetime
    suitability: Suitability
    explanation: str = Field(min_length=1, max_length=500)
    constraints: list[str]
    advisory: Literal[True] = True


class AlternativeEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    name: str
    suitability: Suitability
    mandatory_ok: bool
    explanation: str = Field(min_length=1, max_length=500)
    slots: list[RecommendedSlot]


class SchedulingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    slots: list[RecommendedSlot]
    alternatives: list[AlternativeEquipment]
    constraints: list[str]
    waitlist_eligible: bool
    source: Literal["synthetic"]
    demo: Literal[True]


class WaitlistJoinBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    project_id: RecordId
    duration_minutes: int = Field(ge=15, le=480)
    preferred_start: AwareDatetime
    preferred_end: AwareDatetime
    flexibility_minutes: int = Field(default=0, ge=0, le=1440)


class WaitlistView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RecordId
    equipment_id: RecordId
    project_id: RecordId
    duration_minutes: int
    preferred_start: datetime
    preferred_end: datetime
    flexibility_minutes: int
    status: WaitlistStatus
    created_at: datetime
    updated_at: datetime
    offer_id: RecordId | None
    offered_start: datetime | None
    offered_end: datetime | None
    offer_expires_at: datetime | None
    rank: int | None
    eligible: bool | None
    feasible: bool | None
    provisional: bool | None
    explanation: str | None
    demo: Literal[True]


class WaitlistListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WaitlistView]
    source: Literal["synthetic"]
    demo: Literal[True]


class OfferView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RecordId
    waitlist_id: RecordId
    equipment_id: RecordId
    project_id: RecordId
    start: datetime
    end: datetime
    expires_at: datetime
    status: OfferStatus
    demo: Literal[True]
    note: str


class PromoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId


class PromoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer: OfferView | None
    promoted: bool
    idempotent: bool
    job: Literal["not_deployed"]
    message: str
    demo: Literal[True]


class UtilizationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    percent: float | None = None
    occupied_minutes: int = Field(ge=0)
    available_minutes: int | None = None
    unavailable_reason: str | None = None
    capacity_per_slot: Literal[1]


class AnalyticsCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_total: int = Field(ge=0)
    equipment_active: int = Field(ge=0)
    confirmed_bookings: int = Field(ge=0)
    pending_requests: int = Field(ge=0)
    waitlist_waiting: int = Field(ge=0)
    waitlist_offered: int = Field(ge=0)
    conflicts: int = Field(ge=0)


class DepartmentAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: RecordId
    occupied_minutes: int = Field(ge=0)
    confirmed_bookings: int = Field(ge=0)
    pending_requests: int = Field(ge=0)
    waitlist_waiting: int = Field(ge=0)
    utilization: UtilizationView


class EquipmentAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: RecordId
    name: str
    department_id: RecordId
    category: str
    occupied_minutes: int = Field(ge=0)
    confirmed_bookings: int = Field(ge=0)
    pending_requests: int = Field(ge=0)
    waitlist_waiting: int = Field(ge=0)
    underused: bool
    utilization: UtilizationView


class CategoryDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    pending_requests: int = Field(ge=0)
    waitlist_waiting: int = Field(ge=0)
    confirmed_bookings: int = Field(ge=0)


class ApprovalTurnaround(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_size: int = Field(ge=0)
    median_hours: float | None = None
    unavailable_reason: str | None = None


class AnalyticsOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    counts: AnalyticsCounts
    utilization: UtilizationView
    most_booked: list[EquipmentAnalytics]
    demand_by_category: list[CategoryDemand]
    waitlist_demand: list[EquipmentAnalytics]
    approval_turnaround: ApprovalTurnaround
    source: Literal["synthetic"]
    demo: Literal[True]


class DepartmentAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    items: list[DepartmentAnalytics]
    source: Literal["synthetic"]
    demo: Literal[True]


class EquipmentAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    items: list[EquipmentAnalytics]
    source: Literal["synthetic"]
    demo: Literal[True]
