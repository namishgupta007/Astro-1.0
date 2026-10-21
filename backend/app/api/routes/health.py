"""Health check API route."""

from __future__ import annotations

from fastapi import APIRouter
from app.api.schemas import HealthResponse
from app.storage.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Check API operational health and database connectivity."""
    db_status = "connected"
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "unhealthy"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        version="1.0.0",
        database=db_status,
    )
