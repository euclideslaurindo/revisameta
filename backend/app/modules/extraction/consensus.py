"""Divergences and consensus of a double extraction (block D, docs/modulos.md 7.5.1).

- When both individual extractions are submitted, a project admin opens the
  comparison: every number and category of the two extractors side by side.
- The consensus is created from the first extractor's values (filled in with the
  second's where the first left blanks). Each divergence then needs a decision:
  the value of extractor A, of extractor B, or the value kept in the consensus with
  a justification. The consensus cannot be submitted with undecided divergences.
- Without double extraction, the single extraction becomes the consensus draft
  when it is submitted.
- Agreement (% of equal values and Cohen's kappa on categories) is computed by the
  R service; if R is down the screen still works and says so.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, ServiceUnavailableError
from app.db.base import new_id
from app.integrations.stats_client import StatsClient
from app.modules.auth.models import User
from app.modules.extraction.comparison import (
    DISPERSION_GROUP,
    Comparison,
    Item,
    Snapshot,
    arm_key,
    compare,
    parse_key,
)
from app.modules.extraction.models import (
    DecisionChoice,
    Extraction,
    ExtractionDecision,
    ExtractionKind,
    ExtractionStatus,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.extraction.schemas import FormSchema
from app.modules.extraction.service import current_form
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage
from app.modules.projects.stages import ensure_open
from app.modules.studies.service import get_study

ROW_COPY_FIELDS = (
    "value_type",
    "n",
    "mean",
    "dispersion_type",
    "dispersion_source",
    "sd",
    "se",
    "ci_low",
    "ci_high",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "events",
    "total",
    "t_stat",
    "p_value",
    "effect_reported",
    "adjusted",
    "adjusted_for",
    "source",
    "source_location",
    "annotation_id",
    "direction_confirmed",
)
# A different mean or value type changes the direction sentence.
DIRECTION_FIELDS = {"mean", "value_type"}


# ---- Schemas -------------------------------------------------------------------------


class ExtractorOut(BaseModel):
    id: uuid.UUID
    extraction_id: uuid.UUID
    name: str | None
    side: str  # "a" | "b"


class DecisionOut(BaseModel):
    choice: str
    reason: str | None
    decided_by_name: str | None
    decided_at: datetime


class ItemOut(BaseModel):
    key: str
    section: str
    kind: str
    field: str
    value_a: Any
    value_b: Any
    consensus_value: Any = None
    agree: bool
    divergent: bool
    outcome_id: str | None = None
    arm_key: str | None = None
    arm_label: str | None = None
    group_id: str | None = None
    timepoint: str | None = None
    label_key: str | None = None
    label: str | None = None
    source_a: dict[str, Any] | None = None
    source_b: dict[str, Any] | None = None
    decision: DecisionOut | None = None


class AgreementOut(BaseModel):
    items: int
    agreeing_items: int
    agreement_percent: float
    kappa: float | None
    kappa_items: int
    warnings: list[str]


class ConsensusRef(BaseModel):
    id: uuid.UUID
    status: str
    version: int


class ComparisonOut(BaseModel):
    study_id: uuid.UUID
    double_extraction: bool
    needed: int
    submitted: int
    extractors: list[ExtractorOut]
    consensus: ConsensusRef | None
    items: list[ItemOut]
    divergences: int
    undecided: int
    agreement: AgreementOut | None
    agreement_error: str | None


class DecideIn(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    choice: DecisionChoice
    reason: str | None = Field(default=None, max_length=1000)


# ---- Loading -------------------------------------------------------------------------


def _require_admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


async def snapshot(session: AsyncSession, extraction: Extraction) -> Snapshot:
    arms = list(
        await session.scalars(select(StudyArm).where(StudyArm.extraction_id == extraction.id))
    )
    measures = list(
        await session.scalars(
            select(OutcomeMeasure).where(OutcomeMeasure.extraction_id == extraction.id)
        )
    )
    rows = list(
        await session.scalars(
            select(OutcomeData)
            .where(OutcomeData.extraction_id == extraction.id)
            .order_by(OutcomeData.created_at)
        )
    )
    return Snapshot(dict(extraction.characteristics or {}), arms, measures, rows)


async def _extractions(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> tuple[list[Extraction], Extraction | None]:
    """Submitted individual extractions (oldest first) and the consensus, if any."""
    rows = list(
        await session.scalars(
            select(Extraction)
            .where(Extraction.study_id == study_id, Extraction.project_id == ctx.project.id)
            .order_by(Extraction.created_at)
        )
    )
    individuals = [
        e
        for e in rows
        if e.kind == ExtractionKind.INDIVIDUAL and e.status != ExtractionStatus.DRAFT
    ]
    consensus = next((e for e in rows if e.kind == ExtractionKind.CONSENSUS), None)
    return individuals, consensus


def _needed(ctx: ProjectContext) -> int:
    return 2 if ctx.project.double_extraction else 1


async def _decisions(
    session: AsyncSession, consensus: Extraction | None
) -> dict[str, ExtractionDecision]:
    if consensus is None:
        return {}
    rows = await session.scalars(
        select(ExtractionDecision).where(ExtractionDecision.consensus_id == consensus.id)
    )
    return {d.item_key: d for d in rows}


async def _form(session: AsyncSession, ctx: ProjectContext) -> FormSchema:
    return FormSchema.model_validate((await current_form(session, ctx)).schema)


async def _comparison(
    session: AsyncSession, ctx: ProjectContext, individuals: list[Extraction]
) -> tuple[Comparison, Snapshot, Snapshot]:
    form = await _form(session, ctx)
    a = await snapshot(session, individuals[0])
    b = await snapshot(session, individuals[1])
    return compare(a, b, form), a, b


async def undecided_divergences(
    session: AsyncSession, ctx: ProjectContext, consensus: Extraction
) -> list[str]:
    individuals, _ = await _extractions(session, ctx, consensus.study_id)
    if len(individuals) < 2:
        return []
    comparison, _, _ = await _comparison(session, ctx, individuals[:2])
    decided = await _decisions(session, consensus)
    return [i.key for i in comparison.divergences if i.key not in decided]


# ---- Agreement (R) -------------------------------------------------------------------


async def agreement(
    stats: StatsClient, comparison: Comparison
) -> tuple[AgreementOut | None, str | None]:
    """% agreement over every compared value; Cohen's kappa over categories only."""
    rater_a, rater_b = comparison.codes()
    if not rater_a:
        return None, None
    cat_a, cat_b = comparison.codes(categories_only=True)
    try:
        overall = await stats.kappa(rater_a, rater_b)
        categories = await stats.kappa(cat_a, cat_b) if cat_a else None
    except ServiceUnavailableError:
        return None, "error.stats_unavailable"
    if not overall.ok:
        return None, "error.stats_failed"
    warnings = list(overall.warnings)
    kappa = None
    if categories is not None and categories.ok:
        kappa = categories.result.get("kappa")
        warnings += categories.warnings
    return (
        AgreementOut(
            items=overall.result["items"],
            agreeing_items=overall.result["agreeing_items"],
            agreement_percent=overall.result["agreement_percent"],
            kappa=kappa,
            kappa_items=len(cat_a),
            warnings=[w for w in warnings if w != "kappa_needs_two_items" or kappa is None],
        ),
        None,
    )


# ---- Comparison screen ---------------------------------------------------------------


async def _names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    users = await session.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: u.name for u in users}


def _item_out(item: Item, consensus_value: Any, decision: DecisionOut | None) -> ItemOut:
    return ItemOut(
        key=item.key,
        section=item.section,
        kind=item.kind,
        field=item.field,
        value_a=item.value_a,
        value_b=item.value_b,
        consensus_value=consensus_value,
        agree=item.agree,
        divergent=item.divergent,
        outcome_id=item.outcome_id,
        arm_key=item.arm_key,
        arm_label=item.arm_label,
        group_id=item.group_id,
        timepoint=item.timepoint,
        label_key=item.label_key,
        label=item.label,
        source_a=item.source_a,
        source_b=item.source_b,
        decision=decision,
    )


async def comparison_for_study(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, study_id: uuid.UUID
) -> ComparisonOut:
    _require_admin(ctx)
    await get_study(session, ctx, study_id)
    individuals, consensus = await _extractions(session, ctx, study_id)
    needed = _needed(ctx)
    names = await _names(session, {e.extractor_id for e in individuals if e.extractor_id})
    extractors = [
        ExtractorOut(
            id=e.extractor_id,
            extraction_id=e.id,
            name=names.get(e.extractor_id),
            side="ab"[i],
        )
        for i, e in enumerate(individuals[:2])
        if e.extractor_id is not None
    ]
    out = ComparisonOut(
        study_id=study_id,
        double_extraction=ctx.project.double_extraction,
        needed=needed,
        submitted=len(individuals),
        extractors=extractors,
        consensus=ConsensusRef(id=consensus.id, status=consensus.status, version=consensus.version)
        if consensus
        else None,
        items=[],
        divergences=0,
        undecided=0,
        agreement=None,
        agreement_error=None,
    )
    if len(individuals) < 2:
        return out

    comparison, a, _ = await _comparison(session, ctx, individuals[:2])
    decisions = await _decisions(session, consensus)
    consensus_values: dict[str, Any] = {}
    if consensus is not None:
        form = await _form(session, ctx)
        # Comparing the consensus with extractor A gives the consensus value of each item.
        consensus_values = {
            i.key: i.value_a for i in compare(await snapshot(session, consensus), a, form).items
        }
    decider_names = await _names(session, {d.decided_by for d in decisions.values()})
    items = []
    for item in comparison.items:
        d = decisions.get(item.key)
        decision = (
            DecisionOut(
                choice=d.choice,
                reason=d.reason,
                decided_by_name=decider_names.get(d.decided_by),
                decided_at=d.created_at,
            )
            if d is not None and item.divergent
            else None
        )
        items.append(_item_out(item, consensus_values.get(item.key), decision))
    out.items = items
    out.divergences = len(comparison.divergences)
    out.undecided = len([i for i in comparison.divergences if i.key not in decisions])
    out.agreement, out.agreement_error = await agreement(stats, comparison)
    return out


# ---- Creating the consensus ----------------------------------------------------------


def _copy_arm(ctx: ProjectContext, consensus: Extraction, arm: StudyArm) -> StudyArm:
    return StudyArm(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        extraction_id=consensus.id,
        label=arm.label,
        n=arm.n,
        description=arm.description,
        mapped_group_id=arm.mapped_group_id,
        position=arm.position,
    )


def _copy_measure(ctx: ProjectContext, consensus: Extraction, m: OutcomeMeasure) -> OutcomeMeasure:
    return OutcomeMeasure(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        extraction_id=consensus.id,
        outcome_id=m.outcome_id,
        scale_name=m.scale_name,
        scale_min=m.scale_min,
        scale_max=m.scale_max,
        higher_is_better=m.higher_is_better,
    )


def _copy_row(
    ctx: ProjectContext, consensus: Extraction, row: OutcomeData, arm_id: uuid.UUID
) -> OutcomeData:
    return OutcomeData(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        extraction_id=consensus.id,
        arm_id=arm_id,
        outcome_id=row.outcome_id,
        timepoint=row.timepoint,
        **{f: getattr(row, f) for f in ROW_COPY_FIELDS},
    )


def _by_key(arms: list[StudyArm]) -> dict[str, StudyArm]:
    out: dict[str, StudyArm] = {}
    for arm in sorted(arms, key=lambda a: (a.position, a.created_at)):
        out.setdefault(arm_key(arm), arm)
    return out


async def _build(
    session: AsyncSession,
    ctx: ProjectContext,
    consensus: Extraction,
    sources: list[Snapshot],
) -> None:
    """Copies the first source; the others only fill what the first left out."""
    characteristics: dict[str, Any] = {}
    for src in sources:
        for key, value in src.characteristics.items():
            if characteristics.get(key) in (None, "") and value not in (None, ""):
                characteristics[key] = value
    consensus.characteristics = characteristics

    arms: dict[str, StudyArm] = {}
    for src in sources:
        for key, arm in _by_key(src.arms).items():
            if key not in arms:
                arms[key] = _copy_arm(ctx, consensus, arm)
                session.add(arms[key])
    measures: set[str] = set()
    for src in sources:
        for m in src.measures:
            if str(m.outcome_id) not in measures:
                measures.add(str(m.outcome_id))
                session.add(_copy_measure(ctx, consensus, m))
    await session.flush()
    seen: set[tuple[str, str, str]] = set()
    for src in sources:
        key_of_arm = {str(a.id): arm_key(a) for a in src.arms}
        for row in src.rows:
            akey = key_of_arm.get(str(row.arm_id))
            if akey is None or akey not in arms:
                continue
            rk = (str(row.outcome_id), akey, row.timepoint)
            if rk in seen:
                continue
            seen.add(rk)
            session.add(_copy_row(ctx, consensus, row, arms[akey].id))


async def _new_consensus(
    session: AsyncSession, ctx: ProjectContext, template: Extraction
) -> Extraction:
    consensus = Extraction(
        id=new_id(),
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        study_id=template.study_id,
        form_id=template.form_id,
        extractor_id=None,
        kind=ExtractionKind.CONSENSUS,
        status=ExtractionStatus.DRAFT,
        characteristics={},
    )
    session.add(consensus)
    await session.flush()
    return consensus


async def create_consensus(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> ConsensusRef:
    _require_admin(ctx)
    ensure_open(ctx, Stage.EXTRACTION)
    await get_study(session, ctx, study_id)
    individuals, consensus = await _extractions(session, ctx, study_id)
    if consensus is not None:
        raise AppError("consensus.exists", status_code=409)
    needed = _needed(ctx)
    if len(individuals) < needed:
        raise AppError("consensus.waiting_extractions", status_code=409, needed=needed)
    consensus = await _new_consensus(session, ctx, individuals[0])
    await _build(session, ctx, consensus, [await snapshot(session, e) for e in individuals[:2]])
    await session.commit()
    return ConsensusRef(id=consensus.id, status=consensus.status, version=consensus.version)


async def consensus_from_single(
    session: AsyncSession, ctx: ProjectContext, extraction: Extraction
) -> None:
    """Without double extraction, the submitted extraction becomes the consensus draft;
    whoever submits that draft is recorded as the person who checked it (7.5.1 F)."""
    if ctx.project.double_extraction or extraction.kind != ExtractionKind.INDIVIDUAL:
        return
    _, existing = await _extractions(session, ctx, extraction.study_id)
    if existing is not None:
        return
    consensus = await _new_consensus(session, ctx, extraction)
    await _build(session, ctx, consensus, [await snapshot(session, extraction)])


async def drafts_after_single_mode(session: AsyncSession, ctx: ProjectContext) -> int:
    """Double extraction was just turned off: every study that already has exactly one
    submitted extraction and no consensus gets its consensus draft now, as it would
    have if the extraction had been submitted in single mode. The caller commits."""
    study_ids = set(
        await session.scalars(
            select(Extraction.study_id).where(
                Extraction.project_id == ctx.project.id,
                Extraction.kind == ExtractionKind.INDIVIDUAL,
                Extraction.status != ExtractionStatus.DRAFT,
            )
        )
    )
    created = 0
    for study_id in study_ids:
        individuals, consensus = await _extractions(session, ctx, study_id)
        if consensus is None and len(individuals) == 1:
            await consensus_from_single(session, ctx, individuals[0])
            created += 1
    return created


# ---- Deciding divergences ------------------------------------------------------------


def _row_of(snap: Snapshot, outcome_id: str, akey: str, timepoint: str) -> OutcomeData | None:
    key_of_arm = {str(a.id): arm_key(a) for a in snap.arms}
    return next(
        (
            r
            for r in snap.rows
            if str(r.outcome_id) == outcome_id
            and r.timepoint == timepoint
            and key_of_arm.get(str(r.arm_id)) == akey
        ),
        None,
    )


async def _ensure_arm(
    session: AsyncSession,
    ctx: ProjectContext,
    consensus: Extraction,
    cons: Snapshot,
    side: Snapshot,
    akey: str,
) -> StudyArm | None:
    existing = _by_key(cons.arms).get(akey)
    if existing is not None:
        return existing
    source = _by_key(side.arms).get(akey)
    if source is None:
        return None
    arm = _copy_arm(ctx, consensus, source)
    session.add(arm)
    await session.flush()
    cons.arms.append(arm)
    return arm


async def _apply(
    session: AsyncSession,
    ctx: ProjectContext,
    consensus: Extraction,
    cons: Snapshot,
    side: Snapshot,
    item: Item,
) -> list[str]:
    """Writes the chosen extractor's value into the consensus.

    Returns the keys of other items settled by the same decision (the whole
    dispersion group, or the rows of an arm that is removed).
    """
    parts = parse_key(item.key)
    now = datetime.now(UTC)
    if parts[0] == "char":
        value = side.characteristics.get(parts[1])
        consensus.characteristics = {**consensus.characteristics, parts[1]: value}
        return []

    if parts[0] == "arm":
        akey, name = parts[1], parts[2]
        side_arm = _by_key(side.arms).get(akey)
        cons_arm = _by_key(cons.arms).get(akey)
        if name == "present":
            if side_arm is not None:
                await _ensure_arm(session, ctx, consensus, cons, side, akey)
                return []
            settled: list[str] = []
            if cons_arm is not None:
                cons_arm.deleted_at = now
                for row in cons.rows:
                    if row.arm_id == cons_arm.id:
                        row.deleted_at = now
                        settled.append(f"row|{row.outcome_id}|{akey}|present|{row.timepoint}")
            return settled
        if cons_arm is not None and side_arm is not None:
            cons_arm.n = side_arm.n
        return []

    if parts[0] == "measure":
        outcome_id, name = parts[1], parts[2]
        side_m = next((m for m in side.measures if str(m.outcome_id) == outcome_id), None)
        cons_m = next((m for m in cons.measures if str(m.outcome_id) == outcome_id), None)
        if side_m is None:
            return []
        if cons_m is None:
            cons_m = _copy_measure(ctx, consensus, side_m)
            session.add(cons_m)
            return []
        if name == "higher_is_better" and cons_m.higher_is_better != side_m.higher_is_better:
            for row in cons.rows:
                if str(row.outcome_id) == outcome_id:
                    row.direction_confirmed = False
        setattr(cons_m, name, getattr(side_m, name))
        return []

    # Outcome rows.
    _, outcome_id, akey, name, timepoint = parts
    side_row = _row_of(side, outcome_id, akey, timepoint)
    cons_row = _row_of(cons, outcome_id, akey, timepoint)
    if name == "present":
        if side_row is None:
            if cons_row is not None:
                cons_row.deleted_at = now
            return []
        if cons_row is None:
            arm = await _ensure_arm(session, ctx, consensus, cons, side, akey)
            if arm is not None:
                session.add(_copy_row(ctx, consensus, side_row, arm.id))
        return []
    if side_row is None or cons_row is None:
        return []
    fields = DISPERSION_GROUP if name in DISPERSION_GROUP else (name,)
    for f in fields:
        new = getattr(side_row, f)
        if f in DIRECTION_FIELDS and getattr(cons_row, f) != new:
            cons_row.direction_confirmed = False
        setattr(cons_row, f, new)
    return [f"row|{outcome_id}|{akey}|{f}|{timepoint}" for f in fields if f != name]


async def decide(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: DecideIn
) -> ItemOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.EXTRACTION)
    await get_study(session, ctx, study_id)
    individuals, consensus = await _extractions(session, ctx, study_id)
    if consensus is None:
        raise AppError("consensus.missing", status_code=409)
    if consensus.status != ExtractionStatus.DRAFT:
        raise AppError("extraction.not_editable", status_code=409)
    if len(individuals) < 2:
        raise AppError("consensus.not_double", status_code=409)
    comparison, a, b = await _comparison(session, ctx, individuals[:2])
    by_key = {i.key: i for i in comparison.items}
    item = by_key.get(data.key)
    if item is None or not item.divergent:
        raise AppError("consensus.not_a_divergence", status_code=422)
    reason = (data.reason or "").strip() or None
    if data.choice == DecisionChoice.CONSENSUS and (reason is None or len(reason) < 5):
        raise AppError("consensus.reason_required", status_code=422)

    settled = [item.key]
    if data.choice != DecisionChoice.CONSENSUS:
        side = a if data.choice == DecisionChoice.A else b
        cons = await snapshot(session, consensus)
        settled += await _apply(session, ctx, consensus, cons, side, item)
    consensus.data_version += 1

    decisions = await _decisions(session, consensus)
    for key in settled:
        other = by_key.get(key)
        if other is None or not other.divergent:
            continue
        value = None
        if data.choice == DecisionChoice.A:
            value = other.value_a
        elif data.choice == DecisionChoice.B:
            value = other.value_b
        existing = decisions.get(key)
        if existing is not None:
            existing.choice = data.choice
            existing.value = value
            existing.reason = reason
            existing.decided_by = ctx.user.id
        else:
            session.add(
                ExtractionDecision(
                    project_id=ctx.project.id,
                    created_by=ctx.user.id,
                    consensus_id=consensus.id,
                    item_key=key,
                    choice=data.choice,
                    value=value,
                    reason=reason,
                    decided_by=ctx.user.id,
                )
            )
    await session.commit()

    form = await _form(session, ctx)
    consensus_value = next(
        (
            i.value_a
            for i in compare(await snapshot(session, consensus), a, form).items
            if i.key == item.key
        ),
        None,
    )
    name = (await _names(session, {ctx.user.id})).get(ctx.user.id)
    return _item_out(
        item,
        consensus_value,
        DecisionOut(
            choice=data.choice,
            reason=reason,
            decided_by_name=name,
            decided_at=datetime.now(UTC),
        ),
    )
