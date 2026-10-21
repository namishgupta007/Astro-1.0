"""Indexing jobs API route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from app.api.schemas import JobDetail
from app.storage.repository_store import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    response_model=JobDetail,
    summary="Get status of an indexing job",
)
def get_job_status(job_id: str) -> JobDetail:
    """Retrieve execution status, current stage, and progress of an indexing job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indexing job '{job_id}' not found",
        )
    return JobDetail(**job.to_dict())
