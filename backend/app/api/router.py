"""HTTP routes for the Phase 1 API."""

from fastapi import APIRouter, Request

from app.config import read_settings
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def read_health(request: Request) -> HealthResponse:
    settings = read_settings(request.app.state)
    return HealthResponse(status="ok", service=settings.service_name)
