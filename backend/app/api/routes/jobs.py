"""Indexing jobs API route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
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


@router.get(
    "/{job_id}/stream",
    response_class=StreamingResponse,
    summary="Stream real-time indexing job progress via Server-Sent Events",
    description="Streams indexing stage transitions, progress percentage, and terminal events via SSE.",
)
async def stream_job_events(
    job_id: str,
    request: Request,
    max_events: int | None = None,
):
    """Server-Sent Events endpoint streaming real-time repository analysis telemetry."""
    import asyncio
    import json

    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indexing job '{job_id}' not found",
        )

    async def event_generator():
        last_progress = -1
        last_stage = None
        last_status = None
        attempts = 0
        events_emitted = 0
        max_attempts = 600  # Up to 300 seconds

        while attempts < max_attempts:
            if await request.is_disconnected():
                break

            current_job = get_job(job_id)
            if not current_job:
                payload = {"error": f"Job '{job_id}' not found", "status": "failed"}
                yield f"data: {json.dumps(payload)}\n\n"
                break

            curr_status = current_job.status
            curr_stage = current_job.stage
            curr_progress = current_job.progress

            # Emit event when stage, status, or progress changes, or as periodic heartbeat
            if (
                curr_progress != last_progress
                or curr_stage != last_stage
                or curr_status != last_status
                or attempts % 10 == 0
            ):
                payload = {
                    "job_id": current_job.id,
                    "repository_id": current_job.repository_id,
                    "status": curr_status,
                    "stage": curr_stage,
                    "progress": curr_progress,
                    "started_at": current_job.started_at,
                    "completed_at": current_job.completed_at,
                    "error_message": current_job.error_message,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                events_emitted += 1
                last_progress = curr_progress
                last_stage = curr_stage
                last_status = curr_status

                if max_events is not None and events_emitted >= max_events:
                    break

            if curr_status in ("completed", "failed"):
                break

            await asyncio.sleep(0.5)
            attempts += 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
