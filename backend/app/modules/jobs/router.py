"""Job progress: SSE stream with a polling endpoint as fallback (ADR-005).

The quick Cloudflare tunnel does not support SSE, so the client falls back to
polling GET /jobs/{id} automatically. Both read the same row.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.errors import NotFoundError
from app.db.session import get_session, get_sessionmaker
from app.modules.jobs.models import TERMINAL, BackgroundJob, JobStatus
from app.modules.jobs.schemas_out import job_out
from app.modules.projects.access import ProjectContext, member_access
from app.modules.uploads.schemas import JobOut

router = APIRouter(prefix="/projects/{project_id}/jobs", tags=["jobs"])

SSE_POLL_SECONDS = 1.0
SSE_MAX_SECONDS = 15 * 60


async def _load(session: AsyncSession, project_id: uuid.UUID, job_id: uuid.UUID) -> BackgroundJob:
    job = (
        await session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.id == job_id, BackgroundJob.project_id == project_id
            )
        )
    ).first()
    if job is None:
        raise NotFoundError()
    return job


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> JobOut:
    return job_out(await _load(session, ctx.project.id, job_id))


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    """Emits a `progress` event on every change and closes after the final state."""
    await _load(session, ctx.project.id, job_id)
    project_id = ctx.project.id

    async def stream() -> AsyncIterator[dict[str, str]]:
        last = ""
        waited = 0.0
        while waited < SSE_MAX_SECONDS:
            async with get_sessionmaker()() as fresh:
                job = await _load(fresh, project_id, job_id)
            payload = job_out(job).model_dump_json()
            if payload != last:
                last = payload
                yield {"event": "progress", "data": payload}
            if JobStatus(job.status) in TERMINAL:
                return
            await asyncio.sleep(SSE_POLL_SECONDS)
            waited += SSE_POLL_SECONDS
        yield {"event": "timeout", "data": json.dumps({"id": str(job_id)})}

    return EventSourceResponse(stream(), ping=15)
