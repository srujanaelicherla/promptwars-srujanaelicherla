"""Equipment discovery from the synthetic catalog. No booking or live availability."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import Equipment, EquipmentStatus, RecordId, ResourceKind
from app.schemas import EquipmentListResponse
from app.seed import read_catalog

router = APIRouter()

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 200


def matching_equipment(
    items: list[Equipment],
    *,
    search: str | None,
    department: str | None,
    category: str | None,
    status: EquipmentStatus | None,
    kind: ResourceKind | None,
) -> list[Equipment]:
    """Return catalog matches in id order. Filters combine as a conjunction."""

    needle = None if search is None else search.casefold()
    selected = [
        item
        for item in items
        if (needle is None or needle in item.name.casefold() or needle in item.description.casefold())
        and (department is None or item.department_id == department)
        and (category is None or item.category == category)
        and (status is None or item.status is status)
        and (kind is None or item.kind is kind)
    ]
    selected.sort(key=lambda item: item.id)
    return selected


@router.get("/equipment", response_model=EquipmentListResponse)
def list_equipment(
    request: Request,
    search: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    department: Annotated[RecordId | None, Query()] = None,
    category: Annotated[str | None, Query(min_length=2, max_length=40)] = None,
    status: Annotated[EquipmentStatus | None, Query()] = None,
    kind: Annotated[ResourceKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EquipmentListResponse:
    matched = matching_equipment(
        read_catalog(request.app.state).equipment,
        search=search,
        department=department,
        category=category,
        status=status,
        kind=kind,
    )
    return EquipmentListResponse(
        items=matched[offset : offset + limit],
        total=len(matched),
        limit=limit,
        offset=offset,
        source="synthetic",
    )


@router.get("/equipment/{equipment_id}", response_model=Equipment)
def read_equipment(request: Request, equipment_id: RecordId) -> Equipment:
    for item in read_catalog(request.app.state).equipment:
        if item.id == equipment_id:
            return item
    raise HTTPException(status_code=404)
