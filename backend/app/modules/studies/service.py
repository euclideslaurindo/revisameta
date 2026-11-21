import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.base import new_id
from app.modules.projects.access import ProjectContext
from app.modules.studies.models import Reference, Report, Study, StudyDesign
from app.modules.studies.schemas import (
    ReferenceIn,
    ReferenceOut,
    ReferenceUpdate,
    ReportOut,
    StudyCreate,
    StudyOut,
    StudyUpdate,
)


def _now() -> datetime:
    return datetime.now(UTC)


async def label_taken(
    session: AsyncSession, project_id: uuid.UUID, label: str, exclude: uuid.UUID | None = None
) -> bool:
    query = select(func.count()).where(
        Study.project_id == project_id, func.lower(Study.label) == label.strip().lower()
    )
    if exclude is not None:
        query = query.where(Study.id != exclude)
    return bool(await session.scalar(query))


async def doi_taken(
    session: AsyncSession, project_id: uuid.UUID, doi: str | None, exclude: uuid.UUID | None = None
) -> bool:
    if not doi:
        return False
    query = select(func.count()).where(
        Reference.project_id == project_id, Reference.doi == doi, Reference.search_id.is_(None)
    )
    if exclude is not None:
        query = query.where(Reference.id != exclude)
    return bool(await session.scalar(query))


async def _ensure_label(
    session: AsyncSession, ctx: ProjectContext, label: str, exclude: uuid.UUID | None = None
) -> None:
    if await label_taken(session, ctx.project.id, label, exclude):
        raise AppError("study.duplicate_label", status_code=409)


async def _ensure_doi(
    session: AsyncSession, ctx: ProjectContext, doi: str | None, exclude: uuid.UUID | None = None
) -> None:
    if await doi_taken(session, ctx.project.id, doi, exclude):
        raise AppError("study.duplicate_doi", status_code=409)


async def add_study(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    label: str,
    design: str,
    notes: str | None,
    reference: ReferenceIn,
) -> Study:
    """Adds study + reference + primary report (caller commits).

    Study and reference are flushed first: there are no ORM relationships, so the
    unit of work would not order the inserts by foreign key on its own.
    """
    study = Study(
        id=new_id(),
        project_id=project_id,
        created_by=user_id,
        label=label.strip(),
        design=design,
        notes=notes,
    )
    ref = Reference(
        id=new_id(), project_id=project_id, created_by=user_id, **reference.model_dump()
    )
    session.add_all([study, ref])
    await session.flush()
    session.add(
        Report(
            project_id=project_id,
            created_by=user_id,
            study_id=study.id,
            reference_id=ref.id,
            is_primary=True,
        )
    )
    return study


async def _study_out(session: AsyncSession, studies: list[Study]) -> list[StudyOut]:
    if not studies:
        return []
    rows = await session.execute(
        select(Report, Reference)
        .join(Reference, Reference.id == Report.reference_id)
        .where(Report.study_id.in_([s.id for s in studies]))
        .order_by(Report.is_primary.desc(), Reference.year, Report.created_at)
    )
    by_study: dict[uuid.UUID, list[ReportOut]] = defaultdict(list)
    for report, ref in rows.all():
        by_study[report.study_id].append(
            ReportOut(
                id=report.id,
                is_primary=report.is_primary,
                reference=ReferenceOut.model_validate(ref),
            )
        )
    return [
        StudyOut(
            id=s.id,
            label=s.label,
            design=StudyDesign(s.design),
            notes=s.notes,
            version=s.version,
            reports=by_study[s.id],
        )
        for s in studies
    ]


async def list_studies(session: AsyncSession, ctx: ProjectContext) -> list[StudyOut]:
    studies = (
        await session.scalars(
            select(Study)
            .where(Study.project_id == ctx.project.id)
            .order_by(func.lower(Study.label))
        )
    ).all()
    return await _study_out(session, list(studies))


async def get_study(session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID) -> Study:
    study = (
        await session.scalars(
            select(Study).where(Study.id == study_id, Study.project_id == ctx.project.id)
        )
    ).first()
    if study is None:
        raise NotFoundError()
    return study


async def study_out(session: AsyncSession, study: Study) -> StudyOut:
    return (await _study_out(session, [study]))[0]


async def create_study(session: AsyncSession, ctx: ProjectContext, data: StudyCreate) -> StudyOut:
    await _ensure_label(session, ctx, data.label)
    await _ensure_doi(session, ctx, data.reference.doi)
    study = await add_study(
        session,
        ctx.project.id,
        ctx.user.id,
        data.label,
        data.design.value,
        data.notes,
        data.reference,
    )
    await session.commit()
    return await study_out(session, study)


async def update_study(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: StudyUpdate
) -> StudyOut:
    study = await get_study(session, ctx, study_id)
    if study.version != data.version:
        raise ConflictError()
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if "label" in values:
        await _ensure_label(session, ctx, values["label"], exclude=study.id)
        values["label"] = values["label"].strip()
    if values.get("design") is not None:
        values["design"] = values["design"].value
    for key, value in values.items():
        setattr(study, key, value)
    await session.commit()
    return await study_out(session, study)


async def _reports(session: AsyncSession, study_id: uuid.UUID) -> list[Report]:
    return list(await session.scalars(select(Report).where(Report.study_id == study_id)))


async def delete_study(session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID) -> None:
    study = await get_study(session, ctx, study_id)
    now = _now()
    for report in await _reports(session, study.id):
        report.deleted_at = now
        ref = await session.get(Reference, report.reference_id)
        # A reference from a search stays: it keeps its screening history.
        if ref is not None and ref.search_id is None:
            ref.deleted_at = now
    study.deleted_at = now
    await session.commit()


async def add_report(
    session: AsyncSession,
    ctx: ProjectContext,
    study_id: uuid.UUID,
    reference: ReferenceIn,
    primary: bool,
) -> StudyOut:
    study = await get_study(session, ctx, study_id)
    await _ensure_doi(session, ctx, reference.doi)
    ref = Reference(
        id=new_id(), project_id=ctx.project.id, created_by=ctx.user.id, **reference.model_dump()
    )
    session.add(ref)
    await session.flush()
    if primary:
        for report in await _reports(session, study.id):
            report.is_primary = False
    session.add(
        Report(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            study_id=study.id,
            reference_id=ref.id,
            is_primary=primary,
        )
    )
    await session.commit()
    return await study_out(session, study)


async def remove_report(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, report_id: uuid.UUID
) -> StudyOut:
    study = await get_study(session, ctx, study_id)
    reports = await _reports(session, study.id)
    report = next((r for r in reports if r.id == report_id), None)
    if report is None:
        raise NotFoundError()
    if len(reports) == 1:
        raise AppError("study.last_report", status_code=409)
    report.deleted_at = _now()
    ref = await session.get(Reference, report.reference_id)
    if ref is not None:
        ref.deleted_at = report.deleted_at
    if report.is_primary:
        next(r for r in reports if r.id != report_id).is_primary = True
    await session.commit()
    return await study_out(session, study)


async def merge_studies(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, other_id: uuid.UUID
) -> StudyOut:
    """Same cohort published twice: keep one study, move the other's articles into it."""
    if study_id == other_id:
        raise AppError("error.validation", status_code=422)
    study = await get_study(session, ctx, study_id)
    other = await get_study(session, ctx, other_id)
    for report in await _reports(session, other.id):
        report.study_id = study.id
        report.is_primary = False
    other.deleted_at = _now()
    await session.commit()
    return await study_out(session, study)


async def update_reference(
    session: AsyncSession, ctx: ProjectContext, reference_id: uuid.UUID, data: ReferenceUpdate
) -> ReferenceOut:
    ref = (
        await session.scalars(
            select(Reference).where(
                Reference.id == reference_id, Reference.project_id == ctx.project.id
            )
        )
    ).first()
    if ref is None:
        raise NotFoundError()
    if ref.version != data.version:
        raise ConflictError()
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if "doi" in values:
        await _ensure_doi(session, ctx, values["doi"], exclude=ref.id)
    for key, value in values.items():
        setattr(ref, key, value)
    await session.commit()
    return ReferenceOut.model_validate(ref)
