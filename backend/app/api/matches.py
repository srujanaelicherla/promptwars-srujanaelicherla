"""Project-to-equipment matching from the synthetic catalog."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.matching import MatchResult, rank_matches
from app.models import RecordId
from app.schemas import EquipmentMatch, EquipmentMatchListResponse
from app.seed import read_catalog

router = APIRouter()


def serialize_match(result: MatchResult) -> EquipmentMatch:
    return EquipmentMatch(
        equipment_id=result.equipment.id,
        name=result.equipment.name,
        department_id=result.equipment.department_id,
        score=result.score,
        suitability=result.suitability,
        matched_requirements=list(result.matched_requirements),
        unmet_requirements=list(result.unmet_requirements),
        explanation=result.explanation,
    )


@router.get("/projects/{project_id}/equipment-matches", response_model=EquipmentMatchListResponse)
def list_equipment_matches(
    request: Request,
    project_id: RecordId,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> EquipmentMatchListResponse:
    catalog = read_catalog(request.app.state)
    project = next((item for item in catalog.projects if item.id == project_id), None)
    if project is None:
        raise HTTPException(status_code=404)
    ranked = rank_matches(catalog.equipment, project.required_specifications)
    return EquipmentMatchListResponse(
        project_id=project.id,
        items=[serialize_match(item) for item in ranked[:limit]],
        total=len(ranked),
        limit=limit,
        source="synthetic",
    )
