import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.extraction import service
from app.modules.extraction.models import ExtractionForm
from app.modules.extraction.schemas import (
    ArmIn,
    ArmOut,
    ArmUpdate,
    CharacteristicsUpdate,
    ExtractionDetail,
    ExtractionSummary,
    FormOut,
    FormUpdate,
    MeasureIn,
    MeasureOut,
    OutcomeDataIn,
    OutcomeDataOut,
    OutcomeDataUpdate,
)
from app.modules.projects.access import ProjectContext, admin_access, member_access, project_access
from app.modules.projects.models import Role

router = APIRouter(prefix="/projects/{project_id}", tags=["extraction"])

extractor_access = project_access(Role.EXTRACTOR)


def _form_out(form: ExtractionForm) -> FormOut:
    return FormOut.model_validate(
        {
            "id": form.id,
            "form_version": form.form_version,
            "schema": form.schema,
            "version": form.version,
        }
    )


@router.get("/extraction-form")
async def get_form(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> FormOut:
    return _form_out(await service.current_form(session, ctx))


@router.put("/extraction-form")
async def update_form(
    body: FormUpdate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> FormOut:
    """Saves a new version of the characteristics form."""
    return _form_out(await service.update_form(session, ctx, body))


@router.get("/studies/{study_id}/extractions")
async def list_extractions(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[ExtractionSummary]:
    """Only what the user may see: own extraction, the consensus (admins see all)."""
    return await service.list_for_study(session, ctx, study_id)


@router.post("/studies/{study_id}/extractions", status_code=status.HTTP_201_CREATED)
async def start_extraction(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(extractor_access),
    session: AsyncSession = Depends(get_session),
) -> ExtractionSummary:
    """Starts (or returns) the current user's individual extraction for the study."""
    return await service.start(session, ctx, study_id)


@router.get("/extractions/{extraction_id}")
async def get_extraction(
    extraction_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> ExtractionDetail:
    return await service.detail(session, ctx, extraction_id)


@router.patch("/extractions/{extraction_id}")
async def update_characteristics(
    extraction_id: uuid.UUID,
    body: CharacteristicsUpdate,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> ExtractionSummary:
    return await service.update_characteristics(session, ctx, extraction_id, body)


@router.post("/extractions/{extraction_id}/submit")
async def submit_extraction(
    extraction_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> ExtractionSummary:
    return await service.submit(session, ctx, extraction_id)


@router.post("/extractions/{extraction_id}/arms", status_code=status.HTTP_201_CREATED)
async def add_arm(
    extraction_id: uuid.UUID,
    body: ArmIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> ArmOut:
    return await service.add_arm(session, ctx, extraction_id, body)


@router.patch("/arms/{arm_id}")
async def update_arm(
    arm_id: uuid.UUID,
    body: ArmUpdate,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> ArmOut:
    return await service.update_arm(session, ctx, arm_id, body)


@router.delete("/arms/{arm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_arm(
    arm_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_arm(session, ctx, arm_id)


@router.put("/extractions/{extraction_id}/measures/{outcome_id}")
async def set_measure(
    extraction_id: uuid.UUID,
    outcome_id: uuid.UUID,
    body: MeasureIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> MeasureOut:
    """Scale used by the study for this outcome (name, range, direction)."""
    return await service.set_measure(session, ctx, extraction_id, outcome_id, body)


@router.post("/extractions/{extraction_id}/outcome-data", status_code=status.HTTP_201_CREATED)
async def add_outcome_data(
    extraction_id: uuid.UUID,
    body: OutcomeDataIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> OutcomeDataOut:
    return await service.add_outcome_data(session, ctx, extraction_id, body)


@router.put("/outcome-data/{row_id}")
async def update_outcome_data(
    row_id: uuid.UUID,
    body: OutcomeDataUpdate,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> OutcomeDataOut:
    return await service.update_outcome_data(session, ctx, row_id, body)


@router.delete("/outcome-data/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outcome_data(
    row_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_outcome_data(session, ctx, row_id)
