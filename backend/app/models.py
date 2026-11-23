"""Domain records for LabLink. Validation only; no booking or approval behavior."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

RecordId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=64)]
ActorId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{2,128}$", min_length=2, max_length=128)]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Role(StrEnum):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"


class EquipmentStatus(StrEnum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class ResourceKind(StrEnum):
    EQUIPMENT = "equipment"
    LAB_STATION = "lab-station"
    KIT = "kit"


class BookingStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class Suitability(StrEnum):
    FULLY_SUITABLE = "fully_suitable"
    PARTIALLY_SUITABLE = "partially_suitable"
    UNSUITABLE = "unsuitable"


class SpecComparison(StrEnum):
    EQUAL = "equal"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


class Specification(_Record):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=32)


class Requirement(_Record):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    mandatory: bool = True
    comparison: SpecComparison = SpecComparison.EQUAL


class SafetyPrerequisite(_Record):
    code: RecordId
    description: str = Field(min_length=1, max_length=200)


class Department(_Record):
    id: RecordId
    name: str = Field(min_length=1, max_length=80)


class Lab(_Record):
    id: RecordId
    name: str = Field(min_length=1, max_length=80)
    department_id: RecordId
    location: str = Field(min_length=1, max_length=120)


class User(_Record):
    id: ActorId
    role: Role
    department_id: RecordId


class Equipment(_Record):
    id: RecordId
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=2, max_length=40)
    lab_id: RecordId
    department_id: RecordId
    description: str = Field(min_length=1, max_length=500)
    specifications: list[Specification] = Field(min_length=1, max_length=12)
    status: EquipmentStatus
    safety_prerequisites: list[SafetyPrerequisite] = Field(max_length=8)
    kind: ResourceKind = ResourceKind.EQUIPMENT


class Project(_Record):
    id: RecordId
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    department_id: RecordId
    required_specifications: list[Requirement] = Field(min_length=1, max_length=12)
    deadline: date


class Booking(_Record):
    id: RecordId
    user_id: ActorId
    equipment_id: RecordId
    project_id: RecordId
    start: AwareDatetime
    end: AwareDatetime
    status: BookingStatus
    purpose: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class AccessRequest(_Record):
    id: RecordId
    user_id: ActorId
    project_id: RecordId
    equipment_id: RecordId
    justification: str = Field(min_length=1, max_length=1000)
    status: RequestStatus
    created_at: AwareDatetime
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None

    @model_validator(mode="after")
    def slot_bounds(self) -> Self:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must both be set or both omitted")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class Approval(_Record):
    id: RecordId
    request_id: RecordId
    faculty_id: ActorId
    decision: ApprovalDecision
    comments: str = Field(min_length=1, max_length=500)
    decided_at: AwareDatetime


class AllocationDecision(_Record):
    id: RecordId
    equipment_id: RecordId
    chosen_request_id: RecordId
    faculty_id: ActorId
    explanation: str = Field(min_length=1, max_length=1000)
    competing_request_ids: list[RecordId] = Field(max_length=50)
    created_at: AwareDatetime


class WaitlistStatus(StrEnum):
    WAITING = "waiting"
    OFFERED = "offered"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OfferStatus(StrEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    RELEASED = "released"


class WaitlistEntry(_Record):
    id: RecordId
    user_id: ActorId
    equipment_id: RecordId
    project_id: RecordId
    duration_minutes: int = Field(ge=15, le=480)
    preferred_start: AwareDatetime
    preferred_end: AwareDatetime
    flexibility_minutes: int = Field(default=0, ge=0, le=1440)
    status: WaitlistStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    offer_id: RecordId | None = None
    offered_start: AwareDatetime | None = None
    offered_end: AwareDatetime | None = None
    offer_expires_at: AwareDatetime | None = None


class SlotOffer(_Record):
    id: RecordId
    waitlist_id: RecordId
    user_id: ActorId
    equipment_id: RecordId
    project_id: RecordId
    start: AwareDatetime
    end: AwareDatetime
    expires_at: AwareDatetime
    status: OfferStatus
    created_at: AwareDatetime
