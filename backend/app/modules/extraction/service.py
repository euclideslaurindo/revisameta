"""Extraction rules.

- Individual extractions are blind: only their extractor (and project admins, who
  resolve divergences) can open them. The consensus is visible to every member.
- Only drafts can change; individual by its extractor, consensus by admins.
- Every change to numbers bumps `data_version` (bloco G).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.db.base import new_id
from app.modules.auth.models import User
from app.modules.extraction.checks import impossible_arm_values, impossible_row_values
from app.modules.extraction.models import (
    Extraction,
    ExtractionForm,
    ExtractionKind,
    ExtractionStatus,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.extraction.schemas import (
    DEFAULT_FORM,
    ArmIn,
    ArmOut,
    ArmUpdate,
    CharacteristicsUpdate,
    ExtractionDetail,
    ExtractionSummary,
    FormSchema,
    FormUpdate,
    MeasureIn,
    MeasureOut,
    OutcomeDataIn,
    OutcomeDataOut,
    OutcomeDataUpdate,
    validate_characteristics,
)
from app.modules.pdfs.models import PdfAnnotation, PdfFile
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.studies.models import Report
from app.modules.studies.service import get_study


def _now() -> datetime:
    return datetime.now(UTC)


# ---- Form ---------------------------------------------------------------------------


async def current_form(session: AsyncSession, ctx: ProjectContext) -> ExtractionForm:
    form = (
        await session.scalars(
            select(ExtractionForm).where(
                ExtractionForm.project_id == ctx.project.id, ExtractionForm.is_current.is_(True)
            )
        )
    ).first()
    if form is None:
        form = ExtractionForm(
            id=new_id(),
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            form_version=1,
            schema=DEFAULT_FORM.model_dump(),
            is_current=True,
        )
        session.add(form)
        await session.commit()
    return form


async def update_form(
    session: AsyncSession, ctx: ProjectContext, data: FormUpdate
) -> ExtractionForm:
    """Creates a new version; extractions on older versions are flagged for review."""
    form = await current_form(session, ctx)
    if form.version != data.version:
        raise ConflictError()
    form.is_current = False
    new_form = ExtractionForm(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        form_version=form.form_version + 1,
        schema=data.schema_.model_dump(),
        is_current=True,
    )
    session.add(new_form)
    await session.commit()
    return new_form


# ---- Extractions --------------------------------------------------------------------


def _can_view(ctx: ProjectContext, extraction: Extraction) -> bool:
    if extraction.kind == ExtractionKind.CONSENSUS or ctx.is_admin:
        return True
    return extraction.extractor_id == ctx.user.id


def _ensure_editable(ctx: ProjectContext, extraction: Extraction) -> None:
    if extraction.status != ExtractionStatus.DRAFT:
        raise AppError("extraction.not_editable", status_code=409)
    if extraction.kind == ExtractionKind.CONSENSUS:
        if not ctx.is_admin:
            raise ForbiddenError()
    elif extraction.extractor_id != ctx.user.id:
        raise ForbiddenError()


async def get_extraction(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID
) -> Extraction:
    extraction = (
        await session.scalars(
            select(Extraction).where(
                Extraction.id == extraction_id, Extraction.project_id == ctx.project.id
            )
        )
    ).first()
    if extraction is None or not _can_view(ctx, extraction):
        raise NotFoundError()  # blind: other extractors do not learn it exists
    return extraction


async def _summary(
    session: AsyncSession, ctx: ProjectContext, extraction: Extraction
) -> ExtractionSummary:
    # updated_at is set by the database on update; reload it inside the async context.
    await session.refresh(extraction)
    form = await current_form(session, ctx)
    name = None
    if extraction.extractor_id:
        user = await session.get(User, extraction.extractor_id)
        name = user.name if user else None
    return ExtractionSummary(
        id=extraction.id,
        study_id=extraction.study_id,
        extractor_id=extraction.extractor_id,
        extractor_name=name,
        kind=extraction.kind,
        status=extraction.status,
        form_id=extraction.form_id,
        outdated_form=extraction.form_id != form.id,
        data_version=extraction.data_version,
        version=extraction.version,
        updated_at=extraction.updated_at,
    )


async def list_for_study(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> list[ExtractionSummary]:
    await get_study(session, ctx, study_id)
    rows = await session.scalars(
        select(Extraction)
        .where(Extraction.study_id == study_id, Extraction.project_id == ctx.project.id)
        .order_by(Extraction.created_at)
    )
    return [await _summary(session, ctx, e) for e in rows if _can_view(ctx, e)]


async def start(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> ExtractionSummary:
    if not ({Role.ADMIN, Role.EXTRACTOR} & ctx.roles):
        raise ForbiddenError()
    study = await get_study(session, ctx, study_id)
    existing = list(
        await session.scalars(
            select(Extraction).where(
                Extraction.study_id == study.id, Extraction.kind == ExtractionKind.INDIVIDUAL
            )
        )
    )
    mine = next((e for e in existing if e.extractor_id == ctx.user.id), None)
    if mine is not None:
        return await _summary(session, ctx, mine)
    limit = 2 if ctx.project.double_extraction else 1
    if len(existing) >= limit:
        raise AppError("extraction.enough_extractors", status_code=409, limit=limit)
    form = await current_form(session, ctx)
    extraction = Extraction(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        study_id=study.id,
        form_id=form.id,
        extractor_id=ctx.user.id,
        kind=ExtractionKind.INDIVIDUAL,
        status=ExtractionStatus.DRAFT,
        characteristics={},
    )
    session.add(extraction)
    await session.commit()
    return await _summary(session, ctx, extraction)


async def detail(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID
) -> ExtractionDetail:
    extraction = await get_extraction(session, ctx, extraction_id)
    arms = await session.scalars(
        select(StudyArm)
        .where(StudyArm.extraction_id == extraction.id)
        .order_by(StudyArm.position, StudyArm.created_at)
    )
    measures = await session.scalars(
        select(OutcomeMeasure).where(OutcomeMeasure.extraction_id == extraction.id)
    )
    data = await session.scalars(
        select(OutcomeData)
        .where(OutcomeData.extraction_id == extraction.id)
        .order_by(OutcomeData.created_at)
    )
    summary = await _summary(session, ctx, extraction)
    return ExtractionDetail(
        **summary.model_dump(),
        characteristics=extraction.characteristics,
        arms=[ArmOut.model_validate(a) for a in arms],
        measures=[MeasureOut.model_validate(m) for m in measures],
        outcome_data=[OutcomeDataOut.model_validate(d) for d in data],
    )


async def update_characteristics(
    session: AsyncSession,
    ctx: ProjectContext,
    extraction_id: uuid.UUID,
    data: CharacteristicsUpdate,
) -> ExtractionSummary:
    extraction = await get_extraction(session, ctx, extraction_id)
    _ensure_editable(ctx, extraction)
    if extraction.version != data.version:
        raise ConflictError()
    current = await current_form(session, ctx)
    schema = FormSchema.model_validate(current.schema)
    try:
        cleaned = validate_characteristics(schema, data.characteristics)
    except ValueError as exc:
        raise AppError("extraction.invalid_field", status_code=422, field=str(exc)) from exc
    # Saving under the current form also moves the extraction to the newest version.
    extraction.characteristics = {**extraction.characteristics, **cleaned}
    extraction.form_id = current.id
    await session.commit()
    return await _summary(session, ctx, extraction)


async def submit(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID
) -> ExtractionSummary:
    from app.modules.extraction.alerts import blocking_open

    extraction = await get_extraction(session, ctx, extraction_id)
    _ensure_editable(ctx, extraction)
    if await blocking_open(session, ctx, extraction):
        raise AppError("extraction.open_blocking_alerts", status_code=409)
    extraction.status = ExtractionStatus.SUBMITTED
    await session.commit()
    return await _summary(session, ctx, extraction)


def _reject_impossible(code: str | None) -> None:
    """Values that cannot be true are refused (bloco A, item 2)."""
    if code is not None:
        raise AppError(code, status_code=422)


def _bump(extraction: Extraction) -> None:
    extraction.data_version += 1


# ---- Arms ---------------------------------------------------------------------------


async def _check_group(
    session: AsyncSession, ctx: ProjectContext, group_id: uuid.UUID | None
) -> None:
    if group_id is None:
        return
    found = await session.scalar(
        select(func.count()).where(
            ComparisonGroup.id == group_id, ComparisonGroup.project_id == ctx.project.id
        )
    )
    if not found:
        raise AppError("extraction.unknown_group", status_code=422)


async def add_arm(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID, data: ArmIn
) -> ArmOut:
    extraction = await get_extraction(session, ctx, extraction_id)
    _ensure_editable(ctx, extraction)
    await _check_group(session, ctx, data.mapped_group_id)
    _reject_impossible(impossible_arm_values(data.n))
    arm = StudyArm(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        extraction_id=extraction.id,
        **data.model_dump(),
    )
    session.add(arm)
    _bump(extraction)
    await session.commit()
    return ArmOut.model_validate(arm)


async def _arm(
    session: AsyncSession, ctx: ProjectContext, arm_id: uuid.UUID
) -> tuple[StudyArm, Extraction]:
    arm = (
        await session.scalars(
            select(StudyArm).where(StudyArm.id == arm_id, StudyArm.project_id == ctx.project.id)
        )
    ).first()
    if arm is None:
        raise NotFoundError()
    extraction = await get_extraction(session, ctx, arm.extraction_id)
    _ensure_editable(ctx, extraction)
    return arm, extraction


async def _unconfirm_direction(
    session: AsyncSession, extraction: Extraction, *conditions: Any
) -> None:
    """The direction sentence changed: the extractor must read and confirm it again.

    Done per ORM object so the change goes through the audit log.
    """
    rows = await session.scalars(
        select(OutcomeData).where(
            OutcomeData.extraction_id == extraction.id,
            OutcomeData.direction_confirmed.is_(True),
            *conditions,
        )
    )
    for row in rows:
        row.direction_confirmed = False


async def update_arm(
    session: AsyncSession, ctx: ProjectContext, arm_id: uuid.UUID, data: ArmUpdate
) -> ArmOut:
    arm, extraction = await _arm(session, ctx, arm_id)
    if arm.version != data.version:
        raise ConflictError()
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if "mapped_group_id" in values:
        await _check_group(session, ctx, values["mapped_group_id"])
    if "n" in values:
        _reject_impossible(impossible_arm_values(values["n"]))
    if "mapped_group_id" in values and values["mapped_group_id"] != arm.mapped_group_id:
        await _unconfirm_direction(session, extraction, OutcomeData.arm_id == arm.id)
    for key, value in values.items():
        setattr(arm, key, value)
    _bump(extraction)
    await session.commit()
    return ArmOut.model_validate(arm)


async def delete_arm(session: AsyncSession, ctx: ProjectContext, arm_id: uuid.UUID) -> None:
    arm, extraction = await _arm(session, ctx, arm_id)
    in_use = await session.scalar(select(func.count()).where(OutcomeData.arm_id == arm.id))
    if in_use:
        raise AppError("extraction.arm_in_use", status_code=409)
    arm.deleted_at = _now()
    _bump(extraction)
    await session.commit()


# ---- Scales -------------------------------------------------------------------------


async def _outcome(session: AsyncSession, ctx: ProjectContext, outcome_id: uuid.UUID) -> Outcome:
    outcome = (
        await session.scalars(
            select(Outcome).where(Outcome.id == outcome_id, Outcome.project_id == ctx.project.id)
        )
    ).first()
    if outcome is None:
        raise AppError("extraction.unknown_outcome", status_code=422)
    return outcome


async def set_measure(
    session: AsyncSession,
    ctx: ProjectContext,
    extraction_id: uuid.UUID,
    outcome_id: uuid.UUID,
    data: MeasureIn,
) -> MeasureOut:
    extraction = await get_extraction(session, ctx, extraction_id)
    _ensure_editable(ctx, extraction)
    await _outcome(session, ctx, outcome_id)
    if (
        data.scale_min is not None
        and data.scale_max is not None
        and data.scale_min >= data.scale_max
    ):
        raise AppError("extraction.invalid_scale_range", status_code=422)
    measure = (
        await session.scalars(
            select(OutcomeMeasure).where(
                OutcomeMeasure.extraction_id == extraction.id,
                OutcomeMeasure.outcome_id == outcome_id,
            )
        )
    ).first()
    if measure is None:
        measure = OutcomeMeasure(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            extraction_id=extraction.id,
            outcome_id=outcome_id,
        )
        session.add(measure)
    if measure.higher_is_better != data.higher_is_better:
        await _unconfirm_direction(session, extraction, OutcomeData.outcome_id == outcome_id)
    for key, value in data.model_dump().items():
        setattr(measure, key, value)
    _bump(extraction)
    await session.commit()
    return MeasureOut.model_validate(measure)


# ---- Outcome data -------------------------------------------------------------------


async def _check_annotation(
    session: AsyncSession,
    ctx: ProjectContext,
    extraction: Extraction,
    annotation_id: uuid.UUID | None,
) -> None:
    """The source passage must come from a PDF of this same study."""
    if annotation_id is None:
        return
    found = await session.scalar(
        select(func.count())
        .select_from(PdfAnnotation)
        .join(PdfFile, PdfFile.id == PdfAnnotation.pdf_file_id)
        .join(Report, Report.id == PdfFile.report_id)
        .where(
            PdfAnnotation.id == annotation_id,
            PdfAnnotation.project_id == ctx.project.id,
            Report.study_id == extraction.study_id,
        )
    )
    if not found:
        raise AppError("extraction.unknown_annotation", status_code=422)


async def _check_row(
    session: AsyncSession,
    ctx: ProjectContext,
    extraction: Extraction,
    arm_id: uuid.UUID,
    outcome_id: uuid.UUID,
    timepoint: str,
) -> None:
    arm = await session.scalar(
        select(func.count()).where(StudyArm.id == arm_id, StudyArm.extraction_id == extraction.id)
    )
    if not arm:
        raise AppError("extraction.unknown_arm", status_code=422)
    outcome = await _outcome(session, ctx, outcome_id)
    if outcome.timepoints and timepoint not in outcome.timepoints:
        raise AppError("extraction.unknown_timepoint", status_code=422)


def _values(data: dict[str, Any]) -> dict[str, Any]:
    effect = data.get("effect_reported")
    if effect is not None:
        data["effect_reported"] = {
            k: (str(v) if v is not None and k != "measure" else v) for k, v in effect.items()
        }
    if data.get("dispersion_type") is not None:
        data["dispersion_type"] = str(data["dispersion_type"])
    data["source"] = str(data["source"])
    return data


async def add_outcome_data(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID, data: OutcomeDataIn
) -> OutcomeDataOut:
    extraction = await get_extraction(session, ctx, extraction_id)
    _ensure_editable(ctx, extraction)
    await _check_row(session, ctx, extraction, data.arm_id, data.outcome_id, data.timepoint)
    await _check_annotation(session, ctx, extraction, data.annotation_id)
    _reject_impossible(impossible_row_values(data.model_dump()))
    values = _values(data.model_dump())
    values["value_type"] = str(values["value_type"])
    row = OutcomeData(
        project_id=ctx.project.id, created_by=ctx.user.id, extraction_id=extraction.id, **values
    )
    session.add(row)
    _bump(extraction)
    await session.commit()
    return OutcomeDataOut.model_validate(row)


async def _row(
    session: AsyncSession, ctx: ProjectContext, row_id: uuid.UUID
) -> tuple[OutcomeData, Extraction]:
    row = (
        await session.scalars(
            select(OutcomeData).where(
                OutcomeData.id == row_id, OutcomeData.project_id == ctx.project.id
            )
        )
    ).first()
    if row is None:
        raise NotFoundError()
    extraction = await get_extraction(session, ctx, row.extraction_id)
    _ensure_editable(ctx, extraction)
    return row, extraction


async def update_outcome_data(
    session: AsyncSession, ctx: ProjectContext, row_id: uuid.UUID, data: OutcomeDataUpdate
) -> OutcomeDataOut:
    row, extraction = await _row(session, ctx, row_id)
    if row.version != data.version:
        raise ConflictError()
    timepoint = data.timepoint or row.timepoint
    await _check_row(session, ctx, extraction, row.arm_id, row.outcome_id, timepoint)
    await _check_annotation(session, ctx, extraction, data.values.annotation_id)
    _reject_impossible(impossible_row_values(data.values.model_dump()))
    new_value_type = str(data.value_type) if data.value_type is not None else row.value_type
    if (
        data.values.mean != row.mean
        or timepoint != row.timepoint
        or new_value_type != row.value_type
    ):
        row.direction_confirmed = False
    row.timepoint = timepoint
    if data.value_type is not None:
        row.value_type = str(data.value_type)
    for key, value in _values(data.values.model_dump()).items():
        setattr(row, key, value)
    _bump(extraction)
    await session.commit()
    return OutcomeDataOut.model_validate(row)


async def delete_outcome_data(
    session: AsyncSession, ctx: ProjectContext, row_id: uuid.UUID
) -> None:
    row, extraction = await _row(session, ctx, row_id)
    row.deleted_at = _now()
    _bump(extraction)
    await session.commit()
