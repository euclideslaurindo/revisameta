"""Articles included at full text become studies (docs/modulos.md 7.4; stage 5 step 4).

Approved: a person chooses. An included article either starts a new study, or joins an
existing study as one more report of the same cohort, so the same patients are never
counted twice (study x report).
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.modules.projects.access import ProjectContext
from app.modules.references.service import SearchReferenceOut
from app.modules.screening.service import _ids, _state
from app.modules.studies.models import Report, Study, StudyDesign
from app.modules.studies.schemas import StudyOut
from app.modules.studies.service import _ensure_label, get_study, study_out


class ToStudyIn(BaseModel):
    mode: Literal["new", "attach"]
    label: str | None = Field(default=None, min_length=1, max_length=120)  # new
    design: StudyDesign | None = None  # new
    study_id: uuid.UUID | None = None  # attach
    primary: bool = False  # attach: this article becomes the main report


async def _waiting(session: AsyncSession, ctx: ProjectContext) -> list[uuid.UUID]:
    state = await _state(session, ctx, "full_text")
    included = [
        i
        for i in await _ids(session, ctx, "full_text")
        if state.status(i) in ("include", "resolved_include")
    ]
    linked = set(
        await session.scalars(
            select(Report.reference_id).where(
                Report.project_id == ctx.project.id, Report.reference_id.in_(included)
            )
        )
    )
    return [i for i in included if i not in linked]


async def waiting(session: AsyncSession, ctx: ProjectContext) -> list[SearchReferenceOut]:
    """Included at full text and not yet a study or a report of one."""
    from app.modules.studies.models import Reference

    ids = await _waiting(session, ctx)
    rows = await session.scalars(
        select(Reference).where(Reference.id.in_(ids)).order_by(Reference.id)
    )
    return [SearchReferenceOut.model_validate(r, from_attributes=True) for r in rows]


async def to_study(
    session: AsyncSession, ctx: ProjectContext, reference_id: uuid.UUID, data: ToStudyIn
) -> StudyOut:
    if not ctx.is_admin:
        raise ForbiddenError()
    if reference_id not in await _waiting(session, ctx):
        raise AppError("screening.not_waiting_for_study", status_code=409)
    if data.mode == "new":
        if not data.label or data.design is None:
            raise AppError("screening.study_fields_required", status_code=422)
        await _ensure_label(session, ctx, data.label)
        study = Study(
            project_id=ctx.project.id,
            label=data.label.strip(),
            design=data.design.value,
            created_by=ctx.user.id,
        )
        session.add(study)
        await session.flush()
        primary = True
    else:
        if data.study_id is None:
            raise AppError("screening.study_fields_required", status_code=422)
        study = await get_study(session, ctx, data.study_id)
        primary = data.primary
        if primary:
            for report in await session.scalars(select(Report).where(Report.study_id == study.id)):
                report.is_primary = False
    session.add(
        Report(
            project_id=ctx.project.id,
            study_id=study.id,
            reference_id=reference_id,
            is_primary=primary,
            created_by=ctx.user.id,
        )
    )
    await session.commit()
    return await study_out(session, study)
