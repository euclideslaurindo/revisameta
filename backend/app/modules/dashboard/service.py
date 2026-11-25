"""Project dashboard (docs/modulos.md 7.1): where each stage stands, what is left for each
person and how many days remain until the deadline.

Only counts are shown. Blinding still holds: nobody sees another person's decisions or
answers here, only how many items each person still has to do.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analysis.models import Analysis
from app.modules.auth.models import User
from app.modules.extraction.models import Extraction, ExtractionKind
from app.modules.grade.models import GradeAssessment
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import ProjectMember
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.risk_of_bias import review as rob_review
from app.modules.risk_of_bias.models import RobAssessment
from app.modules.screening import service as screening
from app.modules.studies.models import Study

FINAL = ("submitted", "locked")
StageKey = Literal["protocol", "screening", "extraction", "rob", "analysis", "grade"]
State = Literal["not_started", "in_progress", "done"]


class StageOut(BaseModel):
    key: StageKey
    done: int
    total: int
    state: State
    route: str  # tab of the project that holds the stage


class PersonPending(BaseModel):
    user_id: uuid.UUID
    name: str
    roles: list[str]
    screening_left: int
    extractions_open: int  # individual extractions started and not submitted
    rob_open: int  # individual risk-of-bias assessments started and not submitted


class DashboardOut(BaseModel):
    deadline: date | None
    days_left: int | None  # negative once the deadline has passed
    studies: int
    stages: list[StageOut]
    next_stage: StageKey | None  # first stage not done, in workflow order
    people: list[PersonPending]


def _state(done: int, total: int) -> State:
    if total and done >= total:
        return "done"
    return "in_progress" if done else "not_started"


async def _count(session: AsyncSession, stmt: object) -> int:
    return int(await session.scalar(stmt) or 0)  # type: ignore[call-overload]


async def dashboard(session: AsyncSession, ctx: ProjectContext) -> DashboardOut:
    pid = ctx.project.id
    stages: list[StageOut] = []

    outcomes = await _count(
        session,
        select(func.count())
        .select_from(Outcome)
        .where(Outcome.project_id == pid, Outcome.deleted_at.is_(None)),
    )
    groups = await _count(
        session,
        select(func.count())
        .select_from(ComparisonGroup)
        .where(ComparisonGroup.project_id == pid, ComparisonGroup.deleted_at.is_(None)),
    )
    # The protocol is ready to work with once it has an outcome and two groups to compare.
    protocol_done = int(outcomes > 0) + int(groups >= 2)
    stages.append(
        StageOut(
            key="protocol",
            done=protocol_done,
            total=2,
            state=_state(protocol_done, 2),
            route="protocolo",
        )
    )

    counts = await screening.counts(session, ctx)
    if counts.total:
        decided = counts.total - (counts.pending or 0) - (counts.conflict or 0)
        if counts.pending is None:  # blinded reviewer: only their own progress
            decided = counts.decided_by_me
        stages.append(
            StageOut(
                key="screening",
                done=decided,
                total=counts.total,
                state=_state(decided, counts.total),
                route="triagem",
            )
        )

    studies = list(
        await session.scalars(
            select(Study.id).where(Study.project_id == pid, Study.deleted_at.is_(None))
        )
    )
    extracted = await _count(
        session,
        select(func.count(func.distinct(Extraction.study_id))).where(
            Extraction.project_id == pid,
            Extraction.kind == ExtractionKind.CONSENSUS,
            Extraction.status.in_(FINAL),
            Extraction.study_id.in_(studies),
        ),
    )
    stages.append(
        StageOut(
            key="extraction",
            done=extracted,
            total=len(studies),
            state=_state(extracted, len(studies)),
            route="estudos",
        )
    )

    rob = await rob_review.review(session, ctx)
    stages.append(
        StageOut(
            key="rob",
            done=rob.ready,
            total=rob.total,
            state=_state(rob.ready, rob.total),
            route="risco-de-vies",
        )
    )

    analysed = await _count(
        session,
        select(func.count(func.distinct(Analysis.outcome_id))).where(
            Analysis.project_id == pid, Analysis.deleted_at.is_(None)
        ),
    )
    stages.append(
        StageOut(
            key="analysis",
            done=min(analysed, outcomes),
            total=outcomes,
            state=_state(analysed, outcomes),
            route="meta-analise",
        )
    )
    graded = await _count(
        session,
        select(func.count(func.distinct(GradeAssessment.outcome_id))).where(
            GradeAssessment.project_id == pid, GradeAssessment.deleted_at.is_(None)
        ),
    )
    stages.append(
        StageOut(
            key="grade",
            done=min(graded, outcomes),
            total=outcomes,
            state=_state(graded, outcomes),
            route="grade",
        )
    )

    deadline = ctx.project.deadline
    days_left = (deadline - datetime.now(UTC).date()).days if deadline else None
    return DashboardOut(
        deadline=deadline,
        days_left=days_left,
        studies=len(studies),
        stages=stages,
        next_stage=next((s.key for s in stages if s.state != "done"), None),
        people=await _people(session, ctx),
    )


async def _people(session: AsyncSession, ctx: ProjectContext) -> list[PersonPending]:
    pid = ctx.project.id
    rows = (
        await session.execute(
            select(ProjectMember.user_id, ProjectMember.roles, User.name)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == pid)
            .order_by(User.name)
        )
    ).all()
    extraction_open: dict[uuid.UUID | None, int] = dict(
        (
            await session.execute(
                select(Extraction.extractor_id, func.count())
                .where(
                    Extraction.project_id == pid,
                    Extraction.kind == ExtractionKind.INDIVIDUAL,
                    Extraction.status == "draft",
                    Extraction.deleted_at.is_(None),
                )
                .group_by(Extraction.extractor_id)
            )
        )
        .tuples()
        .all()
    )
    rob_open: dict[uuid.UUID | None, int] = dict(
        (
            await session.execute(
                select(RobAssessment.reviewer_id, func.count())
                .where(
                    RobAssessment.project_id == pid,
                    RobAssessment.kind == "individual",
                    RobAssessment.status == "draft",
                    RobAssessment.deleted_at.is_(None),
                )
                .group_by(RobAssessment.reviewer_id)
            )
        )
        .tuples()
        .all()
    )
    left = await screening.left_per_person(session, ctx, [r.user_id for r in rows])
    return [
        PersonPending(
            user_id=r.user_id,
            name=r.name,
            roles=list(r.roles),
            screening_left=left.get(r.user_id, 0),
            extractions_open=extraction_open.get(r.user_id, 0),
            rob_open=rob_open.get(r.user_id, 0),
        )
        for r in rows
    ]
