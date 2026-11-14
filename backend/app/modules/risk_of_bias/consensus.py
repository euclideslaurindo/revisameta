"""Conflicts, consensus and agreement of the double risk-of-bias assessment (stage 2 step 3).

- When both individual assessments of a study (or of one result) are submitted, a
  project admin compares them question by question and domain by domain.
- The consensus starts from reviewer A's answers (filled in with B's where A left
  blanks). Each conflict then needs a decision: A's value, B's value, or the value
  edited in the consensus with a justification. The consensus cannot be submitted
  with undecided conflicts. Whoever decides is recorded (a third reviewer is an admin).
- Only what each reviewer was actually asked counts: answers to questions skipped by
  the instrument's rules are ignored, so they never show up as false conflicts.
- Agreement (% of equal items and Cohen's kappa) is computed by the R service; if R
  is down the screen still works and says so.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError, ServiceUnavailableError
from app.integrations.stats_client import StatsClient
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage
from app.modules.projects.stages import ensure_open
from app.modules.risk_of_bias import assessments as asm
from app.modules.risk_of_bias.catalog import Template
from app.modules.risk_of_bias.models import (
    RobAnswer,
    RobAssessment,
    RobDecision,
    RobJudgement,
    RobStudyTool,
    RobTool,
)
from app.modules.studies.service import get_study

CHOICES = ("a", "b", "consensus")

# ---- Schemas -------------------------------------------------------------------------


class RobReviewerOut(BaseModel):
    assessment_id: uuid.UUID
    name: str | None
    status: str
    side: str | None  # "a" | "b" once submitted


class RobDecisionOut(BaseModel):
    choice: str
    reason: str | None
    decided_by_name: str | None
    decided_at: datetime


class RobItemOut(BaseModel):
    key: str
    kind: str  # variant | answer | domain | overall
    domain_key: str | None
    question_key: str | None
    outcome_id: uuid.UUID | None
    timepoint: str | None
    value_a: str | None
    value_b: str | None
    consensus_value: str | None
    justification_a: str | None
    justification_b: str | None
    annotation_a: uuid.UUID | None
    annotation_b: uuid.UUID | None
    agree: bool
    decision: RobDecisionOut | None


class RobAgreementOut(BaseModel):
    items: int
    agreeing_items: int
    agreement_percent: float
    kappa: float | None
    warnings: list[str]


class RobConsensusRef(BaseModel):
    id: uuid.UUID
    status: str
    version: int


class RobComparisonOut(BaseModel):
    study_id: uuid.UUID
    tool_id: uuid.UUID
    outcome_id: uuid.UUID | None
    timepoint: str | None
    reviewers: list[RobReviewerOut]
    submitted: int
    consensus: RobConsensusRef | None
    items: list[RobItemOut]
    divergences: int
    undecided: int
    agreement: RobAgreementOut | None
    agreement_error: str | None


class RobConsensusIn(BaseModel):
    outcome_id: uuid.UUID | None = None
    timepoint: str | None = Field(default=None, max_length=60)


class RobDecideIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    choice: str = Field(pattern="^(a|b|consensus)$")
    reason: str | None = Field(default=None, max_length=1000)


class RobProjectAgreementOut(BaseModel):
    pairs: int
    agreement: RobAgreementOut | None
    agreement_error: str | None


# ---- Effective values ----------------------------------------------------------------


class _Side:
    """What one assessment says, item by item (only what the reviewer was asked)."""

    def __init__(
        self,
        a: RobAssessment,
        answers: list[RobAnswer],
        judgements: list[RobJudgement],
        values: dict[str, str | None],
    ) -> None:
        self.assessment = a
        self.answers = {(x.question_key, x.outcome_id, x.timepoint): x for x in answers}
        self.judgements = {j.domain_key: j for j in judgements}
        self.values = values


def answer_key(question_key: str, outcome_id: uuid.UUID | None, timepoint: str | None) -> str:
    return f"answer|{question_key}|{outcome_id or ''}|{timepoint or ''}"


async def _side(
    session: AsyncSession,
    ctx: ProjectContext,
    template: Template,
    tool: RobTool,
    a: RobAssessment,
) -> _Side:
    answers, judgements = await asm._rows(session, a)
    targets = await asm._targets(session, ctx, template)
    domains, overall, _ = asm.compute(template, tool, a, answers, judgements, targets)
    asked = {f"{d.domain_key}.{q}" for d in domains for q in d.asked}
    values: dict[str, str | None] = {}
    for domain in template.domains:
        if domain.variants:
            values[f"variant|{domain.key}"] = (a.variants or {}).get(domain.key)
    for x in answers:
        if x.question_key in asked and x.answer:
            values[answer_key(x.question_key, x.outcome_id, x.timepoint)] = x.answer
    for d in domains:
        if d.final:
            values[f"domain|{d.domain_key}"] = d.final
    if overall.final:
        values["overall"] = overall.final
    return _Side(a, answers, judgements, values)


def _rank(template: Template) -> Any:
    domain_index = {d.key: i for i, d in enumerate(template.domains)}
    question_index = {
        f"{d.key}.{q.key}": j for d in template.domains for j, q in enumerate(d.questions)
    }
    last = len(template.domains)

    def rank(key: str) -> tuple[int, int, int, str, str]:
        parts = key.split("|")
        if parts[0] == "variant":
            return (domain_index.get(parts[1], last), 0, 0, "", "")
        if parts[0] == "answer":
            domain = parts[1].split(".", 1)[0]
            return (
                domain_index.get(domain, last),
                1,
                question_index.get(parts[1], 0),
                parts[2],
                parts[3],
            )
        if parts[0] == "domain":
            return (domain_index.get(parts[1], last), 2, 0, "", "")
        return (last + 1, 3, 0, "", "")

    return rank


def _parse(key: str) -> tuple[str, str | None, str | None, uuid.UUID | None, str | None]:
    """kind, domain_key, question_key, outcome_id, timepoint of an item key."""
    parts = key.split("|")
    if parts[0] == "variant" or parts[0] == "domain":
        return parts[0], parts[1], None, None, None
    if parts[0] == "answer":
        return (
            "answer",
            parts[1].split(".", 1)[0],
            parts[1],
            uuid.UUID(parts[2]) if parts[2] else None,
            parts[3] or None,
        )
    return "overall", None, None, None, None


def _details(side: _Side, key: str) -> tuple[str | None, uuid.UUID | None]:
    kind, domain_key, question_key, outcome_id, timepoint = _parse(key)
    if kind == "answer":
        row = side.answers.get((question_key or "", outcome_id, timepoint))
        return (row.justification, row.annotation_id) if row else (None, None)
    if kind in ("domain", "overall"):
        j = side.judgements.get(domain_key)
        return (j.justification, None) if j else (None, None)
    return None, None


# ---- Loading -------------------------------------------------------------------------


def _require_admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


async def _group(
    session: AsyncSession,
    ctx: ProjectContext,
    study_id: uuid.UUID,
    tool_id: uuid.UUID,
    target: tuple[uuid.UUID | None, str | None],
) -> tuple[list[RobAssessment], RobAssessment | None]:
    """Individual assessments of one target (oldest first) and its consensus."""
    rows = [
        a
        for a in await session.scalars(
            select(RobAssessment)
            .where(
                RobAssessment.project_id == ctx.project.id,
                RobAssessment.study_id == study_id,
                RobAssessment.tool_id == tool_id,
            )
            .order_by(RobAssessment.created_at)
        )
        if (a.outcome_id, a.timepoint) == target
    ]
    individuals = [a for a in rows if a.kind == "individual"]
    consensus = next((a for a in rows if a.kind == "consensus"), None)
    return individuals, consensus


def _submitted(individuals: list[RobAssessment]) -> list[RobAssessment]:
    return [a for a in individuals if a.status != "draft"][:2]


async def _decisions(
    session: AsyncSession, consensus: RobAssessment | None
) -> dict[str, RobDecision]:
    if consensus is None:
        return {}
    rows = await session.scalars(
        select(RobDecision).where(RobDecision.consensus_id == consensus.id)
    )
    return {d.item_key: d for d in rows}


async def _pair(
    session: AsyncSession, ctx: ProjectContext, pair: list[RobAssessment]
) -> tuple[Template, RobTool, _Side, _Side]:
    tool = await asm._tool(session, pair[0])
    template = asm._template(tool)
    a = await _side(session, ctx, template, tool, pair[0])
    b = await _side(session, ctx, template, tool, pair[1])
    return template, tool, a, b


def _divergent_keys(a: _Side, b: _Side) -> list[str]:
    keys = set(a.values) | set(b.values)
    return [k for k in keys if a.values.get(k) != b.values.get(k)]


def _codes(a: _Side, b: _Side, keys: list[str]) -> tuple[list[str], list[str]]:
    return [a.values.get(k) or "-" for k in keys], [b.values.get(k) or "-" for k in keys]


async def _agreement(
    stats: StatsClient, rater_a: list[str], rater_b: list[str]
) -> tuple[RobAgreementOut | None, str | None]:
    if not rater_a:
        return None, None
    try:
        response = await stats.kappa(rater_a, rater_b)
    except ServiceUnavailableError:
        return None, "error.stats_unavailable"
    if not response.ok:
        return None, "error.stats_failed"
    return (
        RobAgreementOut(
            items=response.result["items"],
            agreeing_items=response.result["agreeing_items"],
            agreement_percent=response.result["agreement_percent"],
            kappa=response.result.get("kappa"),
            warnings=list(response.warnings),
        ),
        None,
    )


# ---- Comparison screen ---------------------------------------------------------------


async def _comparison(
    session: AsyncSession,
    ctx: ProjectContext,
    stats: StatsClient | None,
    study_id: uuid.UUID,
    tool_id: uuid.UUID,
    target: tuple[uuid.UUID | None, str | None],
) -> RobComparisonOut:
    individuals, consensus = await _group(session, ctx, study_id, tool_id, target)
    pair = _submitted(individuals)
    names = await asm._names(session, {a.reviewer_id for a in individuals})
    sides = {a.id: "ab"[i] for i, a in enumerate(pair)}
    out = RobComparisonOut(
        study_id=study_id,
        tool_id=tool_id,
        outcome_id=target[0],
        timepoint=target[1],
        reviewers=[
            RobReviewerOut(
                assessment_id=a.id,
                name=names.get(a.reviewer_id) if a.reviewer_id else None,
                status=a.status,
                side=sides.get(a.id),
            )
            for a in individuals
        ],
        submitted=len(pair),
        consensus=RobConsensusRef(id=consensus.id, status=consensus.status, version=consensus.version)
        if consensus
        else None,
        items=[],
        divergences=0,
        undecided=0,
        agreement=None,
        agreement_error=None,
    )
    if len(pair) < 2:
        return out
    template, tool, a, b = await _pair(session, ctx, pair)
    cons = await _side(session, ctx, template, tool, consensus) if consensus else None
    decisions = await _decisions(session, consensus)
    decider_names = await asm._names(session, {d.decided_by for d in decisions.values()})
    keys = sorted(set(a.values) | set(b.values), key=_rank(template))
    items: list[RobItemOut] = []
    for key in keys:
        kind, domain_key, question_key, outcome_id, timepoint = _parse(key)
        agree = a.values.get(key) == b.values.get(key)
        d = decisions.get(key)
        just_a, ann_a = _details(a, key)
        just_b, ann_b = _details(b, key)
        items.append(
            RobItemOut(
                key=key,
                kind=kind,
                domain_key=domain_key,
                question_key=question_key,
                outcome_id=outcome_id,
                timepoint=timepoint,
                value_a=a.values.get(key),
                value_b=b.values.get(key),
                consensus_value=cons.values.get(key) if cons else None,
                justification_a=just_a,
                justification_b=just_b,
                annotation_a=ann_a,
                annotation_b=ann_b,
                agree=agree,
                decision=RobDecisionOut(
                    choice=d.choice,
                    reason=d.reason,
                    decided_by_name=decider_names.get(d.decided_by),
                    decided_at=d.updated_at,
                )
                if d is not None and not agree
                else None,
            )
        )
    out.items = items
    divergent = [i for i in items if not i.agree]
    out.divergences = len(divergent)
    out.undecided = len([i for i in divergent if i.key not in decisions])
    if stats is not None:
        out.agreement, out.agreement_error = await _agreement(stats, *_codes(a, b, keys))
    return out


async def comparisons_for_study(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, study_id: uuid.UUID
) -> list[RobComparisonOut]:
    """One comparison per assessed target (the study, or each outcome and time point)."""
    _require_admin(ctx)
    await get_study(session, ctx, study_id)
    rows = await session.scalars(
        select(RobAssessment)
        .where(
            RobAssessment.project_id == ctx.project.id,
            RobAssessment.study_id == study_id,
            RobAssessment.kind == "individual",
        )
        .order_by(RobAssessment.created_at)
    )
    groups = list(dict.fromkeys((a.tool_id, a.outcome_id, a.timepoint) for a in rows))
    return [
        await _comparison(session, ctx, stats, study_id, tool_id, (outcome_id, timepoint))
        for tool_id, outcome_id, timepoint in groups
    ]


# ---- Creating the consensus ----------------------------------------------------------


def _copy_answer(ctx: ProjectContext, consensus: RobAssessment, x: RobAnswer) -> RobAnswer:
    return RobAnswer(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        assessment_id=consensus.id,
        question_key=x.question_key,
        outcome_id=x.outcome_id,
        timepoint=x.timepoint,
        answer=x.answer,
        justification=x.justification,
        annotation_id=x.annotation_id,
    )


def _copy_judgement(ctx: ProjectContext, consensus: RobAssessment, j: RobJudgement) -> RobJudgement:
    return RobJudgement(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        assessment_id=consensus.id,
        domain_key=j.domain_key,
        final=j.final,
        suggested=j.suggested,
        justification=j.justification,
        direction=j.direction,
    )


async def create_consensus(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: RobConsensusIn
) -> RobComparisonOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    await get_study(session, ctx, study_id)
    target = (data.outcome_id, data.timepoint or None)
    choice = (
        await session.scalars(select(RobStudyTool).where(RobStudyTool.study_id == study_id))
    ).first()
    if choice is None:
        raise AppError("rob.consensus_waiting", status_code=409)
    tool_id = choice.tool_id
    individuals, consensus = await _group(session, ctx, study_id, tool_id, target)
    if consensus is not None:
        raise AppError("rob.consensus_exists", status_code=409)
    pair = _submitted(individuals)
    if len(pair) < 2:
        raise AppError("rob.consensus_waiting", status_code=409)
    consensus = RobAssessment(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        study_id=study_id,
        tool_id=tool_id,
        outcome_id=target[0],
        timepoint=target[1],
        kind="consensus",
        reviewer_id=None,
        status="draft",
        variants={**(pair[1].variants or {}), **(pair[0].variants or {})},
    )
    session.add(consensus)
    await session.flush()
    answers: dict[tuple[str, uuid.UUID | None, str | None], RobAnswer] = {}
    judgements: dict[str | None, RobJudgement] = {}
    for source in pair:  # A first; B only fills what A left blank
        src_answers, src_judgements = await asm._rows(session, source)
        for x in src_answers:
            key = (x.question_key, x.outcome_id, x.timepoint)
            if key not in answers:
                answers[key] = _copy_answer(ctx, consensus, x)
            elif not answers[key].answer and x.answer:
                answers[key].answer = x.answer
                answers[key].justification = x.justification
                answers[key].annotation_id = x.annotation_id
        for j in src_judgements:
            if j.domain_key not in judgements:
                judgements[j.domain_key] = _copy_judgement(ctx, consensus, j)
            elif not judgements[j.domain_key].final and j.final:
                judgements[j.domain_key].final = j.final
                judgements[j.domain_key].justification = j.justification
                judgements[j.domain_key].direction = j.direction
    session.add_all([*answers.values(), *judgements.values()])
    await session.commit()
    return await _comparison(session, ctx, None, study_id, tool_id, target)


# ---- Deciding conflicts --------------------------------------------------------------


async def _consensus(
    session: AsyncSession, ctx: ProjectContext, consensus_id: uuid.UUID
) -> RobAssessment:
    a = await asm.get_assessment(session, ctx, consensus_id)
    if a.kind != "consensus":
        raise NotFoundError()
    return a


async def _apply(
    session: AsyncSession,
    ctx: ProjectContext,
    consensus: RobAssessment,
    side: _Side,
    key: str,
) -> None:
    """Writes the chosen reviewer's item into the consensus."""
    kind, domain_key, question_key, outcome_id, timepoint = _parse(key)
    answers, judgements = await asm._rows(session, consensus)
    if kind == "variant" and domain_key:
        consensus.variants = {
            **(consensus.variants or {}),
            domain_key: side.values.get(key) or "",
        }
        if not consensus.variants[domain_key]:
            del consensus.variants[domain_key]
        return
    if kind == "answer" and question_key:
        src = side.answers.get((question_key, outcome_id, timepoint))
        row = next(
            (
                x
                for x in answers
                if (x.question_key, x.outcome_id, x.timepoint)
                == (question_key, outcome_id, timepoint)
            ),
            None,
        )
        if row is None:
            row = RobAnswer(
                project_id=ctx.project.id,
                created_by=ctx.user.id,
                assessment_id=consensus.id,
                question_key=question_key,
                outcome_id=outcome_id,
                timepoint=timepoint,
            )
            session.add(row)
        row.answer = side.values.get(key)
        row.justification = src.justification if src else None
        row.annotation_id = src.annotation_id if src else None
        return
    src_j = side.judgements.get(domain_key)
    j = next((x for x in judgements if x.domain_key == domain_key), None)
    if j is None:
        j = RobJudgement(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            assessment_id=consensus.id,
            domain_key=domain_key,
        )
        session.add(j)
    j.final = side.values.get(key)
    j.justification = src_j.justification if src_j else None
    j.direction = src_j.direction if src_j else None
    j.suggested = src_j.suggested if src_j else None


async def decide(
    session: AsyncSession,
    ctx: ProjectContext,
    stats: StatsClient,
    consensus_id: uuid.UUID,
    data: RobDecideIn,
) -> RobComparisonOut:
    _require_admin(ctx)
    consensus = await _consensus(session, ctx, consensus_id)
    asm._ensure_editable(ctx, consensus)
    target = (consensus.outcome_id, consensus.timepoint)
    individuals, _ = await _group(session, ctx, consensus.study_id, consensus.tool_id, target)
    pair = _submitted(individuals)
    if len(pair) < 2:
        raise AppError("rob.consensus_waiting", status_code=409)
    _, _, a, b = await _pair(session, ctx, pair)
    if data.key not in _divergent_keys(a, b):
        raise AppError("rob.not_a_conflict", status_code=422)
    reason = (data.reason or "").strip() or None
    if data.choice == "consensus" and (reason is None or len(reason) < 5):
        raise AppError("rob.reason_required", status_code=422)
    value = None
    if data.choice != "consensus":
        side = a if data.choice == "a" else b
        await _apply(session, ctx, consensus, side, data.key)
        value = side.values.get(data.key)
    existing = (await _decisions(session, consensus)).get(data.key)
    if existing is None:
        existing = RobDecision(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            consensus_id=consensus.id,
            item_key=data.key,
        )
        session.add(existing)
    existing.choice = data.choice
    existing.value = value
    existing.reason = reason
    existing.decided_by = ctx.user.id
    existing.updated_at = datetime.now(UTC)
    await session.commit()
    return await _comparison(session, ctx, stats, consensus.study_id, consensus.tool_id, target)


async def undecided_conflicts(
    session: AsyncSession, ctx: ProjectContext, consensus: RobAssessment
) -> int:
    individuals, _ = await _group(
        session,
        ctx,
        consensus.study_id,
        consensus.tool_id,
        (consensus.outcome_id, consensus.timepoint),
    )
    pair = _submitted(individuals)
    if len(pair) < 2:
        return 0
    _, _, a, b = await _pair(session, ctx, pair)
    decided = await _decisions(session, consensus)
    return len([k for k in _divergent_keys(a, b) if k not in decided])


# ---- Project agreement ---------------------------------------------------------------


async def project_agreement(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient
) -> RobProjectAgreementOut:
    """Agreement between reviewers on the domain and overall judgements of every pair."""
    rows = list(
        await session.scalars(
            select(RobAssessment)
            .where(
                RobAssessment.project_id == ctx.project.id,
                RobAssessment.kind == "individual",
                RobAssessment.status != "draft",
            )
            .order_by(RobAssessment.created_at)
        )
    )
    groups: dict[tuple[Any, ...], list[RobAssessment]] = {}
    for row in rows:
        groups.setdefault((row.study_id, row.tool_id, row.outcome_id, row.timepoint), []).append(
            row
        )
    rater_a: list[str] = []
    rater_b: list[str] = []
    pairs = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        pairs += 1
        template, _, a, b = await _pair(session, ctx, group[:2])
        keys = sorted(
            {k for k in set(a.values) | set(b.values) if not k.startswith(("answer", "variant"))},
            key=_rank(template),
        )
        codes_a, codes_b = _codes(a, b, keys)
        rater_a += codes_a
        rater_b += codes_b
    agreement, error = await _agreement(stats, rater_a, rater_b)
    return RobProjectAgreementOut(pairs=pairs, agreement=agreement, agreement_error=error)
