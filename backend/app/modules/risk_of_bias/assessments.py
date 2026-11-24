"""Individual risk-of-bias assessments (docs/modulos.md 7.6, stage 2 step 2).

- A reviewer (or admin) starts an assessment of a study with the instrument the admin
  confirmed. Per-result instruments (RoB 2, ROBINS) are assessed per outcome and time
  point; per-study instruments (JBI, NOS, generic) once, with some questions answered
  per outcome or per result when the instrument says so.
- Assessments are blind: a reviewer only sees their own; admins see all.
- The system suggests domain and overall judgements from the official algorithms (or
  the group's rule for JBI/NOS); the reviewer decides, and disagreeing needs a
  justification (rule 0.2).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.modules.auth.models import User
from app.modules.pdfs.models import PdfAnnotation, PdfFile
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role, Stage
from app.modules.projects.stages import ensure_open
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias.algorithm import (
    is_asked,
    overall_warnings,
    suggest_domain,
    suggest_overall,
)
from app.modules.risk_of_bias.catalog import Domain, Template
from app.modules.risk_of_bias.models import (
    RobAnswer,
    RobAssessment,
    RobJudgement,
    RobStudyTool,
    RobTool,
)
from app.modules.risk_of_bias.rules import evaluate_group_rule, group_levels
from app.modules.studies.models import Report
from app.modules.studies.service import get_study

MAX_REVIEWERS = 2  # double assessment; a third person decides conflicts at consensus

# ---- Schemas -------------------------------------------------------------------------


class StartIn(BaseModel):
    outcome_id: uuid.UUID | None = None
    timepoint: str | None = Field(default=None, max_length=60)


class AnswerIn(BaseModel):
    question_key: str = Field(min_length=3, max_length=80)
    outcome_id: uuid.UUID | None = None
    timepoint: str | None = Field(default=None, max_length=60)
    answer: str | None = Field(default=None, max_length=8)
    justification: str | None = Field(default=None, max_length=4000)
    annotation_id: uuid.UUID | None = None


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=300)


class VariantsIn(BaseModel):
    variants: dict[str, str]


class JudgementIn(BaseModel):
    domain_key: str | None = Field(default=None, max_length=40)  # None = overall
    final: str | None = Field(default=None, max_length=32)
    justification: str | None = Field(default=None, max_length=4000)
    direction: str | None = Field(default=None, max_length=40)


class AnswerOut(BaseModel):
    question_key: str
    outcome_id: uuid.UUID | None
    timepoint: str | None
    answer: str | None
    justification: str | None
    annotation_id: uuid.UUID | None


class DomainState(BaseModel):
    domain_key: str
    variant: str | None
    asked: list[str]  # question keys that apply, given the answers so far
    suggested: str | None
    final: str | None
    justification: str | None
    direction: str | None


class OverallState(BaseModel):
    suggested: str | None
    final: str | None
    justification: str | None
    direction: str | None
    levels: list[str]
    warnings: list[str]


class TargetOut(BaseModel):
    outcome_id: uuid.UUID
    outcome_name: str
    timepoints: list[str]


class AssessmentSummary(BaseModel):
    id: uuid.UUID
    study_id: uuid.UUID
    tool_id: uuid.UUID
    outcome_id: uuid.UUID | None
    timepoint: str | None
    kind: str
    reviewer_id: uuid.UUID | None
    reviewer_name: str | None
    status: str
    version: int


class AssessmentOut(AssessmentSummary):
    template_key: str
    template_version: str
    judgement_kind: str
    variants: dict[str, str]
    answers: list[AnswerOut]
    domains: list[DomainState]
    overall: OverallState
    targets: list[TargetOut]  # per-outcome questions of per-study instruments
    missing: list[str]  # what still blocks submission (codes with params)


# ---- Loading and visibility ------------------------------------------------------------


def reviewers_needed(ctx: ProjectContext) -> int:
    """Submitted individual assessments needed before the consensus (1 or 2)."""
    return MAX_REVIEWERS if ctx.project.double_rob else 1


def _template(tool: RobTool) -> Template:
    return Template.model_validate(tool.structure)


def _can_view(ctx: ProjectContext, a: RobAssessment) -> bool:
    if a.kind != "individual" or ctx.is_admin:
        return True
    return a.reviewer_id == ctx.user.id


async def get_assessment(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID
) -> RobAssessment:
    a = (
        await session.scalars(
            select(RobAssessment).where(
                RobAssessment.id == assessment_id, RobAssessment.project_id == ctx.project.id
            )
        )
    ).first()
    if a is None or not _can_view(ctx, a):
        raise NotFoundError()  # blind: other reviewers do not learn it exists
    return a


async def _tool(session: AsyncSession, a: RobAssessment) -> RobTool:
    tool = await session.get(RobTool, a.tool_id)
    assert tool is not None  # noqa: S101 - foreign key
    return tool


def _ensure_editable(ctx: ProjectContext, a: RobAssessment) -> None:
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    if a.status != "draft":
        raise AppError("rob.not_editable", status_code=409)
    if a.kind == "consensus":
        if not ctx.is_admin:
            raise ForbiddenError()
    elif a.reviewer_id != ctx.user.id:
        raise ForbiddenError()


async def _names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    real = {i for i in ids if i is not None}
    if not real:
        return {}
    return {u.id: u.name for u in await session.scalars(select(User).where(User.id.in_(real)))}


def _summary(a: RobAssessment, names: dict[uuid.UUID, str]) -> AssessmentSummary:
    return AssessmentSummary(
        id=a.id,
        study_id=a.study_id,
        tool_id=a.tool_id,
        outcome_id=a.outcome_id,
        timepoint=a.timepoint,
        kind=a.kind,
        reviewer_id=a.reviewer_id,
        reviewer_name=names.get(a.reviewer_id) if a.reviewer_id else None,
        status=a.status,
        version=a.version,
    )


async def list_for_study(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> list[AssessmentSummary]:
    await get_study(session, ctx, study_id)
    rows = [
        a
        for a in await session.scalars(
            select(RobAssessment)
            .where(RobAssessment.study_id == study_id, RobAssessment.project_id == ctx.project.id)
            .order_by(RobAssessment.created_at)
        )
        if _can_view(ctx, a)
    ]
    names = await _names(session, {a.reviewer_id for a in rows})
    return [_summary(a, names) for a in rows]


# ---- Starting ----------------------------------------------------------------------------


async def start(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: StartIn
) -> AssessmentOut:
    if not ({Role.ADMIN, Role.REVIEWER} & ctx.roles):
        raise ForbiddenError()
    study = await get_study(session, ctx, study_id)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    choice = (
        await session.scalars(select(RobStudyTool).where(RobStudyTool.study_id == study.id))
    ).first()
    if choice is None:
        raise AppError("rob.no_tool_confirmed", status_code=409)
    tool = await session.get(RobTool, choice.tool_id)
    assert tool is not None  # noqa: S101 - foreign key
    template = _template(tool)
    if template.scope == "result":
        if data.outcome_id is None or not data.timepoint:
            raise AppError("rob.result_required", status_code=422)
        outcome = (
            await session.scalars(
                select(Outcome).where(
                    Outcome.id == data.outcome_id, Outcome.project_id == ctx.project.id
                )
            )
        ).first()
        if outcome is None or data.timepoint not in outcome.timepoints:
            raise AppError("rob.unknown_result", status_code=422)
        target: tuple[uuid.UUID | None, str | None] = (data.outcome_id, data.timepoint)
    else:
        target = (None, None)

    same_target = [
        a
        for a in await session.scalars(
            select(RobAssessment).where(
                RobAssessment.study_id == study.id,
                RobAssessment.tool_id == tool.id,
                RobAssessment.kind == "individual",
            )
        )
        if (a.outcome_id, a.timepoint) == target
    ]
    mine = next((a for a in same_target if a.reviewer_id == ctx.user.id), None)
    if mine is None:
        if len(same_target) >= MAX_REVIEWERS:
            raise AppError("rob.enough_reviewers", status_code=409, limit=MAX_REVIEWERS)
        mine = RobAssessment(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            study_id=study.id,
            tool_id=tool.id,
            outcome_id=target[0],
            timepoint=target[1],
            kind="individual",
            reviewer_id=ctx.user.id,
            status="draft",
            variants={},
        )
        session.add(mine)
        await session.commit()
    return await detail(session, ctx, mine.id)


# ---- Computing suggestions -----------------------------------------------------------


def _domain_questions(domain: Domain, variant: str | None) -> list[Any]:
    if not domain.variants:
        return list(domain.questions)
    return [q for q in domain.questions if q.variant == variant]


def _domain_state(
    template: Template,
    domain: Domain,
    variant: str | None,
    answers: dict[str, str | None],
    judgement: RobJudgement | None,
) -> tuple[DomainState, list[str]]:
    """Visible questions, suggestion and what is missing in one domain."""
    missing: list[str] = []
    if domain.variants and variant is None:
        missing.append(f"variant:{domain.key}")
    questions = _domain_questions(domain, variant)
    local = {q.key: answers.get(f"{domain.key}.{q.key}") for q in questions}
    asked = [q.key for q in questions if is_asked(q.ask_if, local)]
    effective = {k: (local[k] if k in asked else "NA") or "" for k in local}
    for key in asked:
        if not local[key]:
            missing.append(f"answer:{domain.key}.{key}")
    suggested = None
    if template.judgement.kind == "algorithm":
        suggested = suggest_domain(domain, effective, template.judgement.levels, variant)
    state = DomainState(
        domain_key=domain.key,
        variant=variant,
        asked=asked,
        suggested=suggested,
        final=judgement.final if judgement else None,
        justification=judgement.justification if judgement else None,
        direction=judgement.direction if judgement else None,
    )
    return state, missing


def compute(
    template: Template,
    tool: RobTool,
    a: RobAssessment,
    answers: list[RobAnswer],
    judgements: list[RobJudgement],
    targets: list[TargetOut],
) -> tuple[list[DomainState], OverallState, list[str]]:
    by_domain = {j.domain_key: j for j in judgements}
    plain = {x.question_key: x.answer for x in answers if x.outcome_id is None}
    per_target = {
        (x.question_key, x.outcome_id, x.timepoint): x.answer
        for x in answers
        if x.outcome_id is not None
    }
    domains: list[DomainState] = []
    missing: list[str] = []
    for domain in template.domains:
        variant = a.variants.get(domain.key) if domain.variants else None
        state, domain_missing = _domain_state(
            template, domain, variant, plain, by_domain.get(domain.key)
        )
        if template.scope == "study":
            # Questions appraised per outcome (or per result) need one answer per target.
            domain_missing = [m for m in domain_missing if not m.startswith("answer:")]
            for q in domain.questions:
                key = f"{domain.key}.{q.key}"
                if q.level == "study":
                    if not plain.get(key):
                        domain_missing.append(f"answer:{key}")
                    continue
                for t in targets:
                    points = t.timepoints if q.level == "result" else [None]
                    for point in points:
                        if not per_target.get((key, t.outcome_id, point)):
                            domain_missing.append(f"answer:{key}")
                            break
        domains.append(state)
        missing += domain_missing

    kind = template.judgement.kind
    overall_j = by_domain.get(None)
    warnings: list[str] = []
    suggested = None
    if kind in ("algorithm", "reviewer"):
        levels = template.judgement.levels
        finals = [d.final for d in domains]
        for d in domains:
            if not d.final:
                missing.append(f"domain:{d.domain_key}")
        if template.judgement.overall and all(finals):
            suggested = suggest_overall(
                template.judgement.overall.rule, [f for f in finals if f], levels
            )
            warnings = overall_warnings(
                [f for f in finals if f], template.judgement.overall.warn_several, suggested
            )
    else:
        levels = group_levels(tool.overall_rule)
        suggested = evaluate_group_rule(tool.overall_rule, template, answers)
    if not overall_j or not overall_j.final:
        missing.append("overall")
    overall = OverallState(
        suggested=suggested,
        final=overall_j.final if overall_j else None,
        justification=overall_j.justification if overall_j else None,
        direction=overall_j.direction if overall_j else None,
        levels=levels,
        warnings=warnings,
    )
    # Disagreeing with a suggestion needs a justification.
    for d in domains:
        if (
            d.suggested
            and d.final
            and d.final != d.suggested
            and not (d.justification or "").strip()
        ):
            missing.append(f"justification:{d.domain_key}")
    if (
        suggested
        and overall.final
        and overall.final != suggested
        and not (overall.justification or "").strip()
    ):
        missing.append("justification:overall")
    return domains, overall, list(dict.fromkeys(missing))


async def _targets(
    session: AsyncSession, ctx: ProjectContext, template: Template
) -> list[TargetOut]:
    if template.scope != "study" or not any(
        q.level != "study" for d in template.domains for q in d.questions
    ):
        return []
    outcomes = await session.scalars(
        select(Outcome).where(Outcome.project_id == ctx.project.id).order_by(Outcome.position)
    )
    return [
        TargetOut(outcome_id=o.id, outcome_name=o.name, timepoints=list(o.timepoints))
        for o in outcomes
    ]


async def _rows(
    session: AsyncSession, a: RobAssessment
) -> tuple[list[RobAnswer], list[RobJudgement]]:
    answers = list(await session.scalars(select(RobAnswer).where(RobAnswer.assessment_id == a.id)))
    judgements = list(
        await session.scalars(select(RobJudgement).where(RobJudgement.assessment_id == a.id))
    )
    return answers, judgements


async def detail(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID
) -> AssessmentOut:
    a = await get_assessment(session, ctx, assessment_id)
    await session.refresh(a)
    tool = await _tool(session, a)
    template = _template(tool)
    answers, judgements = await _rows(session, a)
    targets = await _targets(session, ctx, template)
    domains, overall, missing = compute(template, tool, a, answers, judgements, targets)
    names = await _names(session, {a.reviewer_id})
    return AssessmentOut(
        **_summary(a, names).model_dump(),
        template_key=tool.template_key,
        template_version=tool.template_version,
        judgement_kind=template.judgement.kind,
        variants=a.variants or {},
        answers=[
            AnswerOut(
                question_key=x.question_key,
                outcome_id=x.outcome_id,
                timepoint=x.timepoint,
                answer=x.answer,
                justification=x.justification,
                annotation_id=x.annotation_id,
            )
            for x in answers
        ],
        domains=domains,
        overall=overall,
        targets=targets,
        missing=missing,
    )


# ---- Writing --------------------------------------------------------------------------


def _question_index(template: Template) -> dict[str, tuple[Domain, Any]]:
    return {f"{d.key}.{q.key}": (d, q) for d in template.domains for q in d.questions}


async def _check_annotation(
    session: AsyncSession, ctx: ProjectContext, a: RobAssessment, annotation_id: uuid.UUID | None
) -> None:
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
            Report.study_id == a.study_id,
        )
    )
    if not found:
        raise AppError("rob.unknown_annotation", status_code=422)


async def save_answers(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID, data: AnswersIn
) -> AssessmentOut:
    a = await get_assessment(session, ctx, assessment_id)
    _ensure_editable(ctx, a)
    tool = await _tool(session, a)
    template = _template(tool)
    index = _question_index(template)
    targets = {t.outcome_id: t for t in await _targets(session, ctx, template)}
    existing = {
        (x.question_key, x.outcome_id, x.timepoint): x for x in (await _rows(session, a))[0]
    }
    for item in data.answers:
        found = index.get(item.question_key)
        if found is None:
            raise AppError("rob.unknown_question", status_code=422, key=item.question_key)
        _, question = found
        allowed = template.answer_sets[question.answers]
        if item.answer is not None and item.answer not in allowed:
            raise AppError("rob.invalid_answer", status_code=422, key=item.question_key)
        # Where the answer belongs: the assessment itself, an outcome, or an outcome + time point.
        level = question.level if template.scope == "study" else "study"
        if level == "study":
            if item.outcome_id is not None or item.timepoint is not None:
                raise AppError("rob.wrong_target", status_code=422, key=item.question_key)
        else:
            target = targets.get(item.outcome_id) if item.outcome_id else None
            if target is None:
                raise AppError("rob.wrong_target", status_code=422, key=item.question_key)
            if level == "outcome" and item.timepoint is not None:
                raise AppError("rob.wrong_target", status_code=422, key=item.question_key)
            if level == "result" and item.timepoint not in target.timepoints:
                raise AppError("rob.wrong_target", status_code=422, key=item.question_key)
        await _check_annotation(session, ctx, a, item.annotation_id)
        row = existing.get((item.question_key, item.outcome_id, item.timepoint))
        if row is None:
            row = RobAnswer(
                project_id=ctx.project.id,
                created_by=ctx.user.id,
                assessment_id=a.id,
                question_key=item.question_key,
                outcome_id=item.outcome_id,
                timepoint=item.timepoint,
            )
            session.add(row)
            existing[(item.question_key, item.outcome_id, item.timepoint)] = row
        row.answer = item.answer
        row.justification = (item.justification or "").strip() or None
        row.annotation_id = item.annotation_id
    await session.commit()
    return await detail(session, ctx, a.id)


async def set_variants(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID, data: VariantsIn
) -> AssessmentOut:
    a = await get_assessment(session, ctx, assessment_id)
    _ensure_editable(ctx, a)
    template = _template(await _tool(session, a))
    domains = {d.key: d for d in template.domains}
    variants = dict(a.variants or {})
    for key, variant in data.variants.items():
        domain = domains.get(key)
        if domain is None or variant not in {v.key for v in domain.variants}:
            raise AppError("rob.unknown_variant", status_code=422, key=key)
        variants[key] = variant
    a.variants = variants
    await session.commit()
    return await detail(session, ctx, a.id)


async def set_judgement(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID, data: JudgementIn
) -> AssessmentOut:
    a = await get_assessment(session, ctx, assessment_id)
    _ensure_editable(ctx, a)
    tool = await _tool(session, a)
    template = _template(tool)
    if data.domain_key is not None:
        if template.judgement.kind == "group_rule":
            raise AppError("rob.no_domain_judgement", status_code=422)
        if data.domain_key not in {d.key for d in template.domains}:
            raise AppError("rob.unknown_domain", status_code=422, key=data.domain_key)
        levels = template.judgement.levels
    else:
        levels = (
            template.judgement.levels
            if template.judgement.kind != "group_rule"
            else group_levels(tool.overall_rule)
        )
    if data.final is not None and data.final not in levels:
        raise AppError("rob.invalid_judgement", status_code=422)
    if data.direction is not None and data.direction not in template.judgement.direction:
        raise AppError("rob.invalid_direction", status_code=422)
    answers, judgements = await _rows(session, a)
    targets = await _targets(session, ctx, template)
    domains, overall, _ = compute(template, tool, a, answers, judgements, targets)
    suggested = (
        next((d.suggested for d in domains if d.domain_key == data.domain_key), None)
        if data.domain_key
        else overall.suggested
    )
    row = next((j for j in judgements if j.domain_key == data.domain_key), None)
    if row is None:
        row = RobJudgement(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            assessment_id=a.id,
            domain_key=data.domain_key,
        )
        session.add(row)
    row.final = data.final
    row.suggested = suggested
    row.justification = (data.justification or "").strip() or None
    row.direction = data.direction
    await session.commit()
    return await detail(session, ctx, a.id)


async def submit(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID
) -> AssessmentOut:
    a = await get_assessment(session, ctx, assessment_id)
    _ensure_editable(ctx, a)
    current = await detail(session, ctx, a.id)
    if current.missing:
        raise AppError("rob.incomplete", status_code=409, count=len(current.missing))
    if a.kind == "consensus":
        from app.modules.risk_of_bias.consensus import undecided_conflicts

        undecided = await undecided_conflicts(session, ctx, a)
        if undecided:
            raise AppError("rob.undecided_conflicts", status_code=409, count=undecided)
    a.status = "submitted"
    a.submitted_by = ctx.user.id
    a.submitted_at = datetime.now(UTC)
    await session.commit()
    return await detail(session, ctx, a.id)
