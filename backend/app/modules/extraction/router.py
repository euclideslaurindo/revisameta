import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.extraction import alerts, consensus, service
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


# ---- Safeguards (blocks A and C of 7.5.1) --------------------------------------------


@router.get("/extractions/{extraction_id}/alerts")
async def list_alerts(
    extraction_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[alerts.AlertOut]:
    """Active alerts of the extraction, recomputed from the current data."""
    return await alerts.list_alerts(session, ctx, extraction_id)


@router.post("/alerts/{alert_id}/justify")
async def justify_alert(
    alert_id: uuid.UUID,
    body: alerts.JustifyIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> alerts.AlertOut:
    """Confirms the value with a short justification (recorded in the audit log)."""
    return await alerts.justify(session, ctx, alert_id, body)


@router.get("/pending-checks")
async def pending_checks(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[alerts.PendingAlert]:
    """'Pendências de conferência' of the project (only extractions the user may see)."""
    return await alerts.pending(session, ctx)


@router.get("/extractions/{extraction_id}/direction")
async def direction(
    extraction_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[alerts.DirectionOut]:
    """Data for the direction sentence of each outcome and time point."""
    return await alerts.directions(session, ctx, extraction_id)


@router.post("/extractions/{extraction_id}/direction/confirm")
async def confirm_direction(
    extraction_id: uuid.UUID,
    body: alerts.ConfirmDirectionIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[alerts.DirectionOut]:
    return await alerts.confirm_direction(session, ctx, extraction_id, body)


# ---- Double extraction: divergences and consensus (block D of 7.5.1) -----------------


@router.get("/studies/{study_id}/comparison")
async def study_comparison(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> consensus.ComparisonOut:
    """Both extractors' values side by side, the decisions taken and the agreement."""
    return await consensus.comparison_for_study(session, ctx, stats, study_id)


@router.post("/studies/{study_id}/consensus", status_code=status.HTTP_201_CREATED)
async def create_consensus(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> consensus.ConsensusRef:
    """Creates the consensus once the individual extractions are submitted."""
    return await consensus.create_consensus(session, ctx, study_id)


@router.post("/studies/{study_id}/decisions")
async def decide_divergence(
    study_id: uuid.UUID,
    body: consensus.DecideIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> consensus.ItemOut:
    """Settles one divergence: extractor A's value, B's, or the consensus value (justified)."""
    return await consensus.decide(session, ctx, study_id, body)
