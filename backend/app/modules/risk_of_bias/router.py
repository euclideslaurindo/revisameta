import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.projects.access import ProjectContext, admin_access, member_access
from app.modules.risk_of_bias import assessments, consensus, tools

router = APIRouter(prefix="/projects/{project_id}/rob", tags=["risk_of_bias"])


@router.get("/catalog")
async def rob_catalog(ctx: ProjectContext = Depends(member_access)) -> list[tools.CatalogItem]:
    """Instruments available (structure only; official wording is pasted by the admin)."""
    return tools.catalog_items()


@router.get("/tools")
async def list_rob_tools(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[tools.ToolOut]:
    return [tools.tool_out(t) for t in await tools.project_tools(session, ctx)]


@router.post("/tools", status_code=status.HTTP_201_CREATED)
async def enable_rob_tool(
    body: tools.EnableIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Enables an instrument in the project (a copy that keeps its version)."""
    return await tools.enable(session, ctx, body)


@router.put("/tools/{tool_id}/texts")
async def set_rob_tool_texts(
    tool_id: uuid.UUID,
    body: tools.TextsIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Official wording of the questions, pasted from the official source."""
    return await tools.set_texts(session, ctx, tool_id, body)


@router.put("/tools/{tool_id}/structure")
async def set_rob_tool_structure(
    tool_id: uuid.UUID,
    body: tools.GenericStructureIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Domains of the generic instrument, defined by the group."""
    return await tools.set_generic_structure(session, ctx, tool_id, body)


@router.get("/studies/{study_id}/tool")
async def get_study_rob_tool(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> tools.StudyToolOut:
    """Instrument suggested by the study design and the one confirmed by the admin."""
    return await tools.study_tool(session, ctx, study_id)


@router.put("/studies/{study_id}/tool")
async def confirm_study_rob_tool(
    study_id: uuid.UUID,
    body: tools.StudyToolIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.StudyToolOut:
    return await tools.confirm_study_tool(session, ctx, study_id, body)


@router.put("/tools/{tool_id}/overall-rule")
async def set_rob_overall_rule(
    tool_id: uuid.UUID,
    body: tools.OverallRuleIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """The group's rule for the overall judgement of JBI, Newcastle-Ottawa or generic tools."""
    return await tools.set_overall_rule(session, ctx, tool_id, body)


# ---- Assessments ---------------------------------------------------------------------


@router.get("/studies/{study_id}/assessments")
async def list_rob_assessments(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[assessments.AssessmentSummary]:
    """Assessments of the study the user may see (individual ones are blind)."""
    return await assessments.list_for_study(session, ctx, study_id)


@router.post("/studies/{study_id}/assessments", status_code=status.HTTP_201_CREATED)
async def start_rob_assessment(
    study_id: uuid.UUID,
    body: assessments.StartIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    """Starts (or reopens) the user's own assessment of the study or of one result."""
    return await assessments.start(session, ctx, study_id, body)


@router.get("/assessments/{assessment_id}")
async def get_rob_assessment(
    assessment_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    return await assessments.detail(session, ctx, assessment_id)


@router.put("/assessments/{assessment_id}/answers")
async def save_rob_answers(
    assessment_id: uuid.UUID,
    body: assessments.AnswersIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    """Saves answers (autosave); suggestions are recomputed from them."""
    return await assessments.save_answers(session, ctx, assessment_id, body)


@router.put("/assessments/{assessment_id}/variants")
async def set_rob_variants(
    assessment_id: uuid.UUID,
    body: assessments.VariantsIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    return await assessments.set_variants(session, ctx, assessment_id, body)


@router.put("/assessments/{assessment_id}/judgement")
async def set_rob_judgement(
    assessment_id: uuid.UUID,
    body: assessments.JudgementIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    """Judgement of a domain or overall; disagreeing with the suggestion needs a justification."""
    return await assessments.set_judgement(session, ctx, assessment_id, body)


@router.post("/assessments/{assessment_id}/submit")
async def submit_rob_assessment(
    assessment_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> assessments.AssessmentOut:
    return await assessments.submit(session, ctx, assessment_id)


# ---- Conflicts, consensus and agreement ----------------------------------------------


@router.get("/studies/{study_id}/comparisons")
async def list_rob_comparisons(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> list[consensus.RobComparisonOut]:
    """The two reviewers side by side, per assessed study or result (admins only)."""
    return await consensus.comparisons_for_study(session, ctx, stats, study_id)


@router.post("/studies/{study_id}/consensus", status_code=status.HTTP_201_CREATED)
async def create_rob_consensus(
    study_id: uuid.UUID,
    body: consensus.RobConsensusIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> consensus.RobComparisonOut:
    """Starts the consensus from reviewer A (filled in with B) once both have submitted."""
    return await consensus.create_consensus(session, ctx, study_id, body)


@router.post("/assessments/{assessment_id}/decisions")
async def decide_rob_conflict(
    assessment_id: uuid.UUID,
    body: consensus.RobDecideIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> consensus.RobComparisonOut:
    """Settles one conflict: A's value, B's value, or the consensus value (justified)."""
    return await consensus.decide(session, ctx, stats, assessment_id, body)


@router.get("/agreement")
async def rob_agreement(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> consensus.RobProjectAgreementOut:
    """Agreement between reviewers on domain and overall judgements (% and kappa)."""
    return await consensus.project_agreement(session, ctx, stats)
