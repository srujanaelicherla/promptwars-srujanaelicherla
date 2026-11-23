"""Synthetic catalog. These records are not people, bookings, or approvals from a university."""

from datetime import date, datetime, timezone
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import (
    AccessRequest,
    AllocationDecision,
    Approval,
    ApprovalDecision,
    Booking,
    BookingStatus,
    Department,
    Equipment,
    EquipmentStatus,
    Lab,
    Project,
    RequestStatus,
    Requirement,
    ResourceKind,
    Role,
    SafetyPrerequisite,
    SpecComparison,
    Specification,
    User,
)
from app.synthetic_equipment import extra_equipment, extra_stations_and_kits

_T = TypeVar("_T", bound=BaseModel)


def _spec(name: str, value: str, unit: str | None = None) -> Specification:
    return Specification(name=name, value=value, unit=unit)


def _req(
    name: str,
    value: str,
    unit: str | None = None,
    *,
    mandatory: bool = True,
    comparison: SpecComparison = SpecComparison.EQUAL,
) -> Requirement:
    return Requirement(
        name=name,
        value=value,
        unit=unit,
        mandatory=mandatory,
        comparison=comparison,
    )


def _safety(code: str, description: str) -> SafetyPrerequisite:
    return SafetyPrerequisite(code=code, description=description)


def _at(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _index(items: list[_T], label: str) -> dict[str, _T]:
    found: dict[str, _T] = {}
    for item in items:
        item_id = str(item.id)
        if item_id in found:
            raise ValueError(f"duplicate {label} id: {item_id}")
        found[item_id] = item
    return found


def _require(index: dict[str, _T], item_id: str, label: str) -> _T:
    try:
        return index[item_id]
    except KeyError as exc:
        raise ValueError(f"{label} references unknown id {item_id}") from exc


class Catalog(BaseModel):
    """One consistent set of synthetic records. Foreign keys are checked here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    synthetic: Literal[True]
    departments: list[Department]
    labs: list[Lab]
    users: list[User]
    equipment: list[Equipment]
    projects: list[Project]
    bookings: list[Booking]
    access_requests: list[AccessRequest]
    approvals: list[Approval]
    allocation_decisions: list[AllocationDecision] = []

    @model_validator(mode="after")
    def references_resolve(self) -> "Catalog":
        if self.synthetic is not True:
            raise ValueError("catalog must be marked synthetic")
        departments = _index(self.departments, "department")
        labs = _index(self.labs, "lab")
        users = _index(self.users, "user")
        equipment = _index(self.equipment, "equipment")
        projects = _index(self.projects, "project")
        requests = _index(self.access_requests, "access request")
        _index(self.bookings, "booking")
        _index(self.approvals, "approval")
        _index(self.allocation_decisions, "allocation decision")

        seen = [
            *departments,
            *labs,
            *users,
            *equipment,
            *projects,
            *(item.id for item in self.bookings),
            *requests,
            *(item.id for item in self.approvals),
            *(item.id for item in self.allocation_decisions),
        ]
        if len(seen) != len(set(seen)):
            raise ValueError("record ids must be unique across the catalog")

        for lab in self.labs:
            _require(departments, lab.department_id, "lab")
        for user in self.users:
            _require(departments, user.department_id, "user")
        for item in self.equipment:
            lab = _require(labs, item.lab_id, "equipment")
            _require(departments, item.department_id, "equipment")
            if item.department_id != lab.department_id:
                raise ValueError(f"equipment {item.id} department does not match its lab")
        for project in self.projects:
            _require(departments, project.department_id, "project")
        for booking in self.bookings:
            _require(users, booking.user_id, "booking")
            _require(equipment, booking.equipment_id, "booking")
            _require(projects, booking.project_id, "booking")
        for request in self.access_requests:
            _require(users, request.user_id, "access request")
            _require(projects, request.project_id, "access request")
            _require(equipment, request.equipment_id, "access request")
        for approval in self.approvals:
            _require(requests, approval.request_id, "approval")
            faculty = _require(users, approval.faculty_id, "approval")
            if faculty.role is not Role.FACULTY:
                raise ValueError(f"approval {approval.id} faculty_id is not a faculty user")
        return self


def load_seed() -> Catalog:
    """Return the built-in synthetic catalog."""

    return Catalog(
        synthetic=True,
        departments=[
            Department(id="dept-physics", name="Physics"),
            Department(id="dept-chemistry", name="Chemistry"),
            Department(id="dept-biology", name="Biology"),
            Department(id="dept-engineering", name="Engineering"),
        ],
        labs=[
            Lab(
                id="lab-optics",
                name="Optics laboratory",
                department_id="dept-physics",
                location="Science Hall 210",
            ),
            Lab(
                id="lab-analytical",
                name="Analytical laboratory",
                department_id="dept-chemistry",
                location="Science Hall 114",
            ),
            Lab(
                id="lab-maker",
                name="Electronics and fabrication laboratory",
                department_id="dept-engineering",
                location="Engineering 040",
            ),
            Lab(
                id="lab-biology",
                name="Cell and molecular laboratory",
                department_id="dept-biology",
                location="Life Sciences 118",
            ),
        ],
        users=[
            User(id="user-admin", role=Role.ADMIN, department_id="dept-engineering"),
            User(id="user-faculty-physics", role=Role.FACULTY, department_id="dept-physics"),
            User(id="user-faculty-engineering", role=Role.FACULTY, department_id="dept-engineering"),
            User(id="user-faculty-chemistry", role=Role.FACULTY, department_id="dept-chemistry"),
            User(id="user-faculty-biology", role=Role.FACULTY, department_id="dept-biology"),
            User(id="user-student-physics", role=Role.STUDENT, department_id="dept-physics"),
            User(id="user-student-chemistry", role=Role.STUDENT, department_id="dept-chemistry"),
            User(id="user-student-engineering", role=Role.STUDENT, department_id="dept-engineering"),
        ],
        equipment=[
            Equipment(
                id="eq-diode-laser",
                name="Diode laser",
                category="optics",
                lab_id="lab-optics",
                department_id="dept-physics",
                description="Continuous-wave green diode laser for alignment and spectroscopy.",
                specifications=[
                    _spec("wavelength", "532", "nm"),
                    _spec("output power", "50", "mW"),
                    _spec("laser class", "3B"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("laser-safety", "Laser safety training for class 3B sources."),
                    _safety("eye-protection", "Wavelength-rated eyewear worn while the beam is enabled."),
                ],
            ),
            Equipment(
                id="eq-optical-table",
                name="Optical table",
                category="optics",
                lab_id="lab-optics",
                department_id="dept-physics",
                description="Pneumatically isolated table for optical layouts.",
                specifications=[
                    _spec("length", "2.4", "m"),
                    _spec("width", "1.2", "m"),
                    _spec("isolation", "pneumatic"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("lab-induction", "Optics laboratory induction, including beam-path rules."),
                ],
            ),
            Equipment(
                id="eq-spectrometer",
                name="UV-Vis spectrometer",
                category="spectroscopy",
                lab_id="lab-optics",
                department_id="dept-physics",
                description="Benchtop spectrometer for absorbance measurements.",
                specifications=[
                    _spec("wavelength range", "190-1100", "nm"),
                    _spec("bandwidth", "1", "nm"),
                    _spec("detector", "UV-Vis"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("optical-safety", "Do not look into the sample beam."),
                    _safety("chemical-hygiene", "Chemical hygiene training before liquid samples."),
                ],
            ),
            Equipment(
                id="eq-hplc",
                name="HPLC system",
                category="chromatography",
                lab_id="lab-analytical",
                department_id="dept-chemistry",
                description="High-performance liquid chromatography system with a UV-Vis detector.",
                specifications=[
                    _spec("flow rate", "0.001-10", "mL/min"),
                    _spec("detector", "UV-Vis"),
                    _spec("pressure limit", "60", "MPa"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("chemical-hygiene", "Chemical hygiene training."),
                    _safety("solvent-handling", "Training for flammable HPLC solvents and waste."),
                ],
            ),
            Equipment(
                id="eq-fume-hood",
                name="Chemical fume hood",
                category="safety",
                lab_id="lab-analytical",
                department_id="dept-chemistry",
                description="Ducted hood for volatile solvent work.",
                specifications=[
                    _spec("face velocity", "0.5", "m/s"),
                    _spec("sash width", "1.5", "m"),
                ],
                status=EquipmentStatus.MAINTENANCE,
                safety_prerequisites=[
                    _safety("chemical-hygiene", "Chemical hygiene training."),
                    _safety("hood-use", "Fume hood use includes sash height and airflow check."),
                ],
            ),
            Equipment(
                id="eq-balance",
                name="Analytical balance",
                category="measurement",
                lab_id="lab-analytical",
                department_id="dept-chemistry",
                description="Enclosed balance for milligram-scale sample preparation.",
                specifications=[
                    _spec("readability", "0.01", "mg"),
                    _spec("capacity", "220", "g"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("lab-induction", "Analytical laboratory induction."),
                ],
            ),
            Equipment(
                id="eq-oscilloscope",
                name="Digital oscilloscope",
                category="electronics",
                lab_id="lab-maker",
                department_id="dept-engineering",
                description="Four-channel oscilloscope for circuit bring-up.",
                specifications=[
                    _spec("bandwidth", "200", "MHz"),
                    _spec("channels", "4"),
                    _spec("sample rate", "2", "GSa/s"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("electrical-safety", "Low-voltage electrical safety training."),
                ],
            ),
            Equipment(
                id="eq-cnc-mill",
                name="Benchtop CNC mill",
                category="fabrication",
                lab_id="lab-maker",
                department_id="dept-engineering",
                description="Enclosed benchtop mill for small metal and plastic parts.",
                specifications=[
                    _spec("travel", "400 x 300 x 250", "mm"),
                    _spec("spindle speed", "10000", "rpm"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[
                    _safety("machine-shop", "Machine shop authorization for the CNC mill."),
                    _safety("eye-protection", "Safety glasses required while the spindle runs."),
                ],
            ),
            Equipment(
                id="eq-workbench",
                name="Open workbench",
                category="workspace",
                lab_id="lab-maker",
                department_id="dept-engineering",
                description="Unrestricted bench for low-risk layout work. No specialized training is recorded.",
                specifications=[
                    _spec("length", "1.8", "m"),
                    _spec("width", "0.9", "m"),
                ],
                status=EquipmentStatus.AVAILABLE,
                safety_prerequisites=[],
                kind=ResourceKind.LAB_STATION,
            ),
            *extra_equipment(),
            *extra_stations_and_kits(),
        ],
        projects=[
            Project(
                id="proj-raman",
                title="Raman alignment exercise",
                description="Synthetic optics exercise that needs a green laser and a stable table.",
                department_id="dept-physics",
                required_specifications=[
                    _req("wavelength", "532", "nm"),
                    _req("length", "2.4", "m"),
                ],
                deadline=date(2026, 12, 18),
            ),
            Project(
                id="proj-hplc-method",
                title="Caffeine method sketch",
                description="Synthetic chromatography exercise for a UV-Vis HPLC method.",
                department_id="dept-chemistry",
                required_specifications=[
                    _req("detector", "UV-Vis"),
                    _req("flow rate", "1", "mL/min"),
                ],
                deadline=date(2027, 1, 20),
            ),
            Project(
                id="proj-sensor",
                title="Sensor board bring-up",
                description="Synthetic electronics exercise for a four-channel measurement setup.",
                department_id="dept-engineering",
                required_specifications=[
                    _req("bandwidth", "100", "MHz", comparison=SpecComparison.AT_LEAST),
                    _req("channels", "4"),
                ],
                deadline=date(2026, 12, 10),
            ),
            Project(
                id="proj-amplicon",
                title="Synthetic amplicon exercise",
                description="Synthetic molecular-biology exercise that needs a heated-lid 96-well thermocycler. Not a live study.",
                department_id="dept-biology",
                required_specifications=[
                    _req("well format", "96-well"),
                    _req("heated lid", "yes"),
                ],
                deadline=date(2027, 2, 15),
            ),
        ],
        bookings=[
            Booking(
                id="book-raman",
                user_id="user-student-physics",
                equipment_id="eq-diode-laser",
                project_id="proj-raman",
                start=_at(2026, 12, 2, 9),
                end=_at(2026, 12, 2, 11),
                status=BookingStatus.REQUESTED,
            ),
            Booking(
                id="book-scope",
                user_id="user-student-engineering",
                equipment_id="eq-oscilloscope",
                project_id="proj-sensor",
                start=_at(2026, 12, 3, 13),
                end=_at(2026, 12, 3, 15),
                status=BookingStatus.APPROVED,
            ),
        ],
        access_requests=[
            AccessRequest(
                id="req-hplc",
                user_id="user-student-chemistry",
                project_id="proj-hplc-method",
                equipment_id="eq-hplc",
                justification="Synthetic request for the sample HPLC exercise. Not a real access request.",
                status=RequestStatus.PENDING,
                created_at=_at(2026, 11, 20, 9),
                start=_at(2026, 12, 8, 10),
                end=_at(2026, 12, 8, 12),
            ),
            AccessRequest(
                id="req-spectrometer",
                user_id="user-student-physics",
                project_id="proj-raman",
                equipment_id="eq-spectrometer",
                justification="Synthetic request for the sample spectroscopy exercise. Not a real access request.",
                status=RequestStatus.APPROVED,
                created_at=_at(2026, 11, 10, 9),
                start=_at(2026, 12, 4, 10),
                end=_at(2026, 12, 4, 12),
            ),
        ],
        approvals=[
            Approval(
                id="appr-spectrometer",
                request_id="req-spectrometer",
                faculty_id="user-faculty-physics",
                decision=ApprovalDecision.APPROVED,
                comments="Synthetic approval recorded only so the sample data links together.",
                decided_at=_at(2026, 11, 12, 14),
            ),
        ],
    )


def read_catalog(state: object) -> Catalog:
    """Return the catalog stored on the application, or fail closed."""

    catalog = getattr(state, "catalog", None)
    if not isinstance(catalog, Catalog):
        raise RuntimeError("Application catalog is not configured")
    return catalog
