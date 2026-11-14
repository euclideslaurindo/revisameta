"""Persistence of extraction alerts and of the direction confirmation (blocks A and C)."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.modules.extraction.checks import (
    DIRECTION_UNCONFIRMED,
    Alert,
    compute_alerts,
    direction_summaries,
)
from app.modules.extraction.models import (
    AlertStatus,
    CheckAlert,
    Extraction,
    ExtractionKind,
    ExtractionStatus,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.extraction.service import get_extraction
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import ComparisonGroup, Outcome


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    extraction_id: uuid.UUID
    code: str
    severity: str
    target_type: str
    target_id: uuid.UUID
    field: str | None
    params: dict[str, Any]
    status: str
    justification: str | None
    version: int


class PendingAlert(AlertOut):
    study_id: uuid.UUID
    study_label: str


class JustifyIn(BaseModel):
    justification: str = Field(min_length=5, max_length=1000)


class DirectionSideOut(BaseModel):
    arm_id: str
    arm_label: str
    group_label: str
    mean: str


class DirectionOut(BaseModel):
    outcome_id: str
    outcome_name: str
    timepoint: str
    scale_name: str | None
    higher_is_better: bool
    first: DirectionSideOut
    second: DirectionSideOut
    favors: str
    confirmed: bool


class ConfirmDirectionIn(BaseModel):
    outcome_id: uuid.UUID
    timepoint: str = Field(min_length=1, max_length=60)


async def _inputs(
    session: AsyncSession, ctx: ProjectContext, extraction: Extraction
) -> dict[str, Any]:
    arms = list(
        await session.scalars(select(StudyArm).where(StudyArm.extraction_id == extraction.id))
    )
    measures = list(
        await session.scalars(
            select(OutcomeMeasure).where(OutcomeMeasure.extraction_id == extraction.id)
        )
    )
    rows = list(
        await session.scalars(select(OutcomeData).where(OutcomeData.extraction_id == extraction.id))
    )
    outcomes = list(
        await session.scalars(
            select(Outcome).where(Outcome.project_id == ctx.project.id).order_by(Outcome.position)
        )
    )
    groups = list(
        await session.scalars(
            select(ComparisonGroup).where(ComparisonGroup.project_id == ctx.project.id)
        )
    )
    return {
        "arms": arms,
        "measures": measures,
        "rows": rows,
        "outcomes": outcomes,
        "groups": groups,
    }


async def sync_alerts(
    session: AsyncSession, ctx: ProjectContext, extraction: Extraction
) -> list[CheckAlert]:
    """Brings the stored alerts in line with the current data and returns the active ones."""
    data = await _inputs(session, ctx, extraction)
    current: dict[tuple[str, str, str, str | None], Alert] = {
        a.key: a
        for a in compute_alerts(
            extraction_id=str(extraction.id), characteristics=extraction.characteristics, **data
        )
    }
    stored = list(
        await session.scalars(
            select(CheckAlert).where(
                CheckAlert.extraction_id == extraction.id, CheckAlert.status != AlertStatus.RESOLVED
            )
        )
    )
    seen: set[tuple[str, str, str, str | None]] = set()
    for row in stored:
        key = (row.code, row.target_type, str(row.target_id), row.field)
        alert = current.get(key)
        if alert is None:
            row.status = AlertStatus.RESOLVED
            continue
        seen.add(key)
        if row.params != alert.params:
            # The values behind the alert changed: a previous justification no longer applies.
            row.params = alert.params
            row.status = AlertStatus.OPEN
            row.justification = None
            row.decided_by = None
    for key, alert in current.items():
        if key in seen:
            continue
        session.add(
            CheckAlert(
                project_id=ctx.project.id,
                extraction_id=extraction.id,
                code=alert.code,
                severity=alert.severity,
                target_type=alert.target_type,
                target_id=uuid.UUID(alert.target_id),
                field=alert.field,
                params=alert.params,
                status=AlertStatus.OPEN,
            )
        )
    await session.commit()
    rows = await session.scalars(
        select(CheckAlert)
        .where(CheckAlert.extraction_id == extraction.id, CheckAlert.status != AlertStatus.RESOLVED)
        .order_by(CheckAlert.severity, CheckAlert.created_at)
    )
    return list(rows)


async def list_alerts(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID
) -> list[AlertOut]:
    extraction = await get_extraction(session, ctx, extraction_id)
    return [AlertOut.model_validate(a) for a in await sync_alerts(session, ctx, extraction)]


def _can_decide(ctx: ProjectContext, extraction: Extraction) -> bool:
    if extraction.kind == ExtractionKind.CONSENSUS:
        return ctx.is_admin
    return extraction.extractor_id == ctx.user.id


async def justify(
    session: AsyncSession, ctx: ProjectContext, alert_id: uuid.UUID, data: JustifyIn
) -> AlertOut:
    """Confirms a value that triggered an alert. The justification goes to the audit log."""
    alert = (
        await session.scalars(
            select(CheckAlert).where(
                CheckAlert.id == alert_id, CheckAlert.project_id == ctx.project.id
            )
        )
    ).first()
    if alert is None:
        raise NotFoundError()
    extraction = await get_extraction(session, ctx, alert.extraction_id)
    if not _can_decide(ctx, extraction):
        raise ForbiddenError()
    if extraction.status != ExtractionStatus.DRAFT:
        raise AppError("extraction.not_editable", status_code=409)
    if alert.status == AlertStatus.RESOLVED:
        raise AppError("extraction.alert_resolved", status_code=409)
    if alert.code == DIRECTION_UNCONFIRMED:
        # The direction is confirmed by reading the sentence, not by a justification.
        raise AppError("extraction.alert_confirm_direction", status_code=409)
    alert.status = AlertStatus.JUSTIFIED
    alert.justification = data.justification.strip()
    alert.decided_by = ctx.user.id
    await session.commit()
    return AlertOut.model_validate(alert)


async def pending(session: AsyncSession, ctx: ProjectContext) -> list[PendingAlert]:
    """'Pendências de conferência': open alerts of every extraction the user may see."""
    from app.modules.studies.models import Study

    extractions = list(
        await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id, Extraction.status == ExtractionStatus.DRAFT
            )
        )
    )
    visible = [
        e
        for e in extractions
        if e.kind == ExtractionKind.CONSENSUS or ctx.is_admin or e.extractor_id == ctx.user.id
    ]
    labels = {
        s.id: s.label
        for s in await session.scalars(select(Study).where(Study.project_id == ctx.project.id))
    }
    result: list[PendingAlert] = []
    for extraction in visible:
        for alert in await sync_alerts(session, ctx, extraction):
            if alert.status == AlertStatus.OPEN:
                result.append(
                    PendingAlert(
                        **AlertOut.model_validate(alert).model_dump(),
                        study_id=extraction.study_id,
                        study_label=labels.get(extraction.study_id, ""),
                    )
                )
    return result


async def blocking_open(session: AsyncSession, ctx: ProjectContext, extraction: Extraction) -> bool:
    alerts = await sync_alerts(session, ctx, extraction)
    return any(a.severity == "block" and a.status == AlertStatus.OPEN for a in alerts)


async def directions(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID
) -> list[DirectionOut]:
    extraction = await get_extraction(session, ctx, extraction_id)
    data = await _inputs(session, ctx, extraction)
    return [
        DirectionOut.model_validate(s, from_attributes=True) for s in direction_summaries(**data)
    ]


async def confirm_direction(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID, data: ConfirmDirectionIn
) -> list[DirectionOut]:
    """The extractor read the sentence and agrees the numbers point the right way."""
    extraction = await get_extraction(session, ctx, extraction_id)
    if not _can_decide(ctx, extraction):
        raise ForbiddenError()
    if extraction.status != ExtractionStatus.DRAFT:
        raise AppError("extraction.not_editable", status_code=409)
    summary = next(
        (
            s
            for s in await directions(session, ctx, extraction_id)
            if s.outcome_id == str(data.outcome_id) and s.timepoint == data.timepoint
        ),
        None,
    )
    if summary is None:
        raise NotFoundError()
    rows = await session.scalars(
        select(OutcomeData).where(
            OutcomeData.extraction_id == extraction.id,
            OutcomeData.outcome_id == data.outcome_id,
            OutcomeData.timepoint == data.timepoint,
            OutcomeData.arm_id.in_(
                [uuid.UUID(summary.first.arm_id), uuid.UUID(summary.second.arm_id)]
            ),
        )
    )
    for row in rows:  # one by one, so the confirmation is recorded in the audit log
        row.direction_confirmed = True
    await session.commit()
    return await directions(session, ctx, extraction_id)
