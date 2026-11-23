"""Title and abstract screening (docs/modulos.md 7.3; stage 5 step 3).

Rules:
- Who screens: admins and reviewers. If a reference was given to specific reviewers
  (a batch), only they (and admins) decide on it (lesson L9).
- Blinding (on by default): a reviewer sees only their own decisions, also through the
  API. The admin sees everything and turns blinding off when the reviewers finished.
- Result of a reference (approved): two "include" pass, two "exclude" leave, any other
  combination (any "maybe" included) is a conflict for an admin to resolve.
- Decisions are never edited or erased: a new one supersedes the previous and "undo"
  withdraws the latest, bringing the one before back (lesson L6).
- References removed as duplicates or with their search are not screened.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError, ServiceUnavailableError
from app.integrations.stats_client import StatsClient
from app.modules.auth.models import User
from app.modules.notifications.service import admins_of, notify
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import ProjectMember, Role
from app.modules.references.service import SearchReferenceOut
from app.modules.screening.models import (
    ExclusionReason,
    ScreeningAssignment,
    ScreeningDecision,
    ScreeningResolution,
)
from app.modules.studies.models import Reference

Stage = Literal["title_abstract", "full_text"]
SCREENERS = {Role.ADMIN, Role.REVIEWER}
REQUIRED = 2  # double screening

Decision = Literal["include", "exclude", "maybe"]
Status = Literal[
    "pending", "include", "exclude", "conflict", "resolved_include", "resolved_exclude"
]


class ScreeningSettings(BaseModel):
    include_keywords: list[str] = Field(default_factory=list, max_length=100)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=100)
    blind: bool = True


class ScreeningDecisionOut(BaseModel):
    id: uuid.UUID
    reference_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    decision: str
    note: str | None
    exclusion_reason_id: uuid.UUID | None = None
    created_at: datetime
    current: bool
    undone: bool


class ScreeningQueueItem(BaseModel):
    reference: SearchReferenceOut
    useful_as_reference: bool
    my_decision: str | None
    my_reason_id: uuid.UUID | None = None
    priority_score: float | None = None
    decisions: int  # how many reviewers decided (always visible)
    status: Status | None  # None while blind for this user
    others: list[ScreeningDecisionOut]  # other reviewers' current decisions; empty while blind
    assigned_to: list[uuid.UUID]


class ScreeningQueuePage(BaseModel):
    items: list[ScreeningQueueItem]
    total: int
    next_cursor: uuid.UUID | None  # import order
    next_offset: int | None = None  # priority order


class ScreeningCounts(BaseModel):
    total: int  # references to screen (no duplicates)
    decided_by_me: int
    left_for_me: int
    include: int | None  # None while blind for this user
    exclude: int | None
    conflict: int | None
    pending: int | None
    resolved: int | None


class ScreeningDecideIn(BaseModel):
    decision: Decision
    note: str | None = Field(default=None, max_length=1000)
    exclusion_reason_id: uuid.UUID | None = None  # required to exclude at full text


class ScreeningResolveIn(BaseModel):
    decision: Literal["include", "exclude"]
    reason: str = Field(min_length=3, max_length=1000)
    exclusion_reason_id: uuid.UUID | None = None  # required to exclude at full text


class ScreeningUsefulIn(BaseModel):
    useful: bool


class ScreeningAssignIn(BaseModel):
    user_id: uuid.UUID
    count: int = Field(ge=1, le=5000)


class ScreeningAssignmentSummary(BaseModel):
    user_id: uuid.UUID
    user_name: str
    assigned: int
    decided: int


class ScreeningAgreementOut(BaseModel):
    user_a: uuid.UUID
    user_b: uuid.UUID
    name_a: str
    name_b: str
    items: int
    agreement_percent: float | None
    kappa: float | None
    warnings: list[str]


# ---- Helpers -------------------------------------------------------------------------


def settings_of(ctx: ProjectContext) -> ScreeningSettings:
    return ScreeningSettings.model_validate(ctx.project.screening_settings or {})


def _sees_all(ctx: ProjectContext) -> bool:
    return ctx.is_admin or not settings_of(ctx).blind


def _can_screen(ctx: ProjectContext) -> None:
    if not (SCREENERS & ctx.roles):
        raise ForbiddenError()


def status_of(
    decisions: list[str],
    resolution: str | None,
    reasons: list[uuid.UUID | None] | None = None,
) -> Status:
    if resolution == "include":
        return "resolved_include"
    if resolution == "exclude":
        return "resolved_exclude"
    if len(decisions) < REQUIRED:
        return "pending"
    if all(d == "include" for d in decisions):
        return "include"
    if all(d == "exclude" for d in decisions):
        # Full text: both excluded but for different reasons is a conflict too, because
        # the PRISMA flow diagram needs one reason per article.
        if reasons and len(set(reasons)) > 1:
            return "conflict"
        return "exclude"
    return "conflict"


def _active(ctx: ProjectContext) -> list[Any]:
    return [
        Reference.project_id == ctx.project.id,
        Reference.search_id.is_not(None),
        Reference.duplicate_of.is_(None),
    ]


async def _reference(
    session: AsyncSession, ctx: ProjectContext, ref_id: uuid.UUID, stage: Stage = "title_abstract"
) -> Reference:
    ref = (
        await session.scalars(select(Reference).where(Reference.id == ref_id, *_active(ctx)))
    ).first()
    if ref is None or (stage == "full_text" and ref_id not in await _eligible(session, ctx)):
        raise NotFoundError()
    return ref


async def _eligible(session: AsyncSession, ctx: ProjectContext) -> set[uuid.UUID]:
    """References that passed title and abstract screening (they go to full text)."""
    state = await _state(session, ctx, "title_abstract")
    return {
        ref_id
        for ref_id in state.decisions.keys() | state.resolutions.keys()
        if state.status(ref_id) in ("include", "resolved_include")
    }


async def _ids(
    session: AsyncSession, ctx: ProjectContext, stage: Stage, *where: Any
) -> list[uuid.UUID]:
    ids = list(
        await session.scalars(
            select(Reference.id).where(*_active(ctx), *where).order_by(Reference.id)
        )
    )
    if stage == "full_text":
        eligible = await _eligible(session, ctx)
        ids = [i for i in ids if i in eligible]
    return ids


class _State:
    """Current decisions, resolutions and assignments of the whole project, in memory
    (a few tens of thousands of small rows at most)."""

    def __init__(self) -> None:
        self.decisions: dict[uuid.UUID, dict[uuid.UUID, ScreeningDecision]] = defaultdict(dict)
        self.resolutions: dict[uuid.UUID, str] = {}
        self.resolution_reasons: dict[uuid.UUID, uuid.UUID | None] = {}
        self.assigned: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)

    def status(self, ref_id: uuid.UUID) -> Status:
        current = list(self.decisions.get(ref_id, {}).values())
        return status_of(
            [d.decision for d in current],
            self.resolutions.get(ref_id),
            [d.exclusion_reason_id for d in current],
        )

    def reason(self, ref_id: uuid.UUID) -> uuid.UUID | None:
        """The exclusion reason of an excluded reference (full text): agreed or resolved."""
        if ref_id in self.resolutions:
            return self.resolution_reasons.get(ref_id)
        reasons = {d.exclusion_reason_id for d in self.decisions.get(ref_id, {}).values()}
        return next(iter(reasons)) if len(reasons) == 1 else None


async def _state(session: AsyncSession, ctx: ProjectContext, stage: Stage) -> _State:
    state = _State()
    for d in await session.scalars(
        select(ScreeningDecision).where(
            ScreeningDecision.project_id == ctx.project.id,
            ScreeningDecision.stage == stage,
            ScreeningDecision.superseded_at.is_(None),
        )
    ):
        state.decisions[d.reference_id][d.user_id] = d
    for r in await session.scalars(
        select(ScreeningResolution).where(
            ScreeningResolution.project_id == ctx.project.id, ScreeningResolution.stage == stage
        )
    ):
        state.resolutions[r.reference_id] = r.decision
        state.resolution_reasons[r.reference_id] = r.exclusion_reason_id
    for a in await session.scalars(
        select(ScreeningAssignment).where(
            ScreeningAssignment.project_id == ctx.project.id, ScreeningAssignment.stage == stage
        )
    ):
        state.assigned[a.reference_id].add(a.user_id)
    return state


def _decision_out(
    d: ScreeningDecision, names: dict[uuid.UUID, str] | None = None
) -> ScreeningDecisionOut:
    return ScreeningDecisionOut(
        id=d.id,
        reference_id=d.reference_id,
        user_id=d.user_id,
        user_name=(names or {}).get(d.user_id),
        decision=d.decision,
        note=d.note,
        exclusion_reason_id=d.exclusion_reason_id,
        created_at=d.created_at,
        current=d.superseded_at is None,
        undone=d.undone,
    )


async def _names(session: AsyncSession, ctx: ProjectContext) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(User.id, User.name)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == ctx.project.id)
    )
    return {uid: name for uid, name in rows.all()}


# ---- Settings ------------------------------------------------------------------------


async def update_settings(
    session: AsyncSession, ctx: ProjectContext, data: ScreeningSettings
) -> ScreeningSettings:
    if not ctx.is_admin:
        raise ForbiddenError()
    clean = ScreeningSettings(
        include_keywords=sorted({k.strip() for k in data.include_keywords if k.strip()}),
        exclude_keywords=sorted({k.strip() for k in data.exclude_keywords if k.strip()}),
        blind=data.blind,
    )
    # Keep what is not a setting (e.g. the prioritization model info).
    ctx.project.screening_settings = {
        **(ctx.project.screening_settings or {}),
        **clean.model_dump(),
    }
    await session.commit()
    return clean


# ---- Queue and counts ----------------------------------------------------------------

View = Literal["todo", "done", "conflicts", "all"]


async def queue(
    session: AsyncSession,
    ctx: ProjectContext,
    view: View,
    after: uuid.UUID | None,
    limit: int,
    search: str | None = None,
    stage: Stage = "title_abstract",
    order: Literal["import", "priority"] = "import",
    offset: int = 0,
) -> ScreeningQueuePage:
    state = await _state(session, ctx, stage)
    me = ctx.user.id
    sees_all = _sees_all(ctx)
    if view == "conflicts" and not sees_all:
        raise ForbiddenError()
    where: list[Any] = []
    if search:
        pattern = f"%{search.strip()}%"
        where.append(Reference.title.ilike(pattern) | Reference.abstract.ilike(pattern))
    ids = await _ids(session, ctx, stage, *where)

    def keep(ref_id: uuid.UUID) -> bool:
        mine = me in state.decisions.get(ref_id, {})
        if view == "todo":
            assigned = state.assigned.get(ref_id)
            allowed = not assigned or me in assigned
            return not mine and allowed and not state.resolutions.get(ref_id)
        if view == "done":
            return mine
        if view == "conflicts":
            return state.status(ref_id) == "conflict"
        return True

    selected = [i for i in ids if keep(i)]
    total = len(selected)
    next_offset: int | None = None
    if order == "priority":
        # Highest predicted chance of inclusion first; references without a score
        # (imported after the last training) keep import order at the end.
        scores = dict(
            (
                await session.execute(
                    select(Reference.id, Reference.priority_score).where(*_active(ctx))
                )
            ).all()
        )
        selected.sort(key=lambda i: (scores.get(i) is None, -(scores.get(i) or 0.0), i))
        page_ids = selected[offset : offset + limit]
        more = False
        next_offset = offset + limit if offset + limit < total else None
    else:
        if after is not None:
            selected = [i for i in selected if i > after]
        page_ids = selected[: limit + 1]
        more = len(page_ids) > limit
        page_ids = page_ids[:limit]
    refs = {
        r.id: r for r in await session.scalars(select(Reference).where(Reference.id.in_(page_ids)))
    }
    names = await _names(session, ctx) if sees_all else {}
    items = []
    for ref_id in page_ids:
        ref = refs[ref_id]
        current = state.decisions.get(ref_id, {})
        mine = current.get(me)
        items.append(
            ScreeningQueueItem(
                reference=SearchReferenceOut.model_validate(ref, from_attributes=True),
                useful_as_reference=ref.useful_as_reference,
                priority_score=ref.priority_score,
                my_decision=mine.decision if mine else None,
                my_reason_id=mine.exclusion_reason_id if mine else None,
                decisions=len(current),
                status=state.status(ref_id) if sees_all else None,
                others=[_decision_out(d, names) for uid, d in current.items() if uid != me]
                if sees_all
                else [],
                assigned_to=sorted(state.assigned.get(ref_id, set())),
            )
        )
    return ScreeningQueuePage(
        items=items,
        total=total,
        next_cursor=page_ids[-1] if more and page_ids else None,
        next_offset=next_offset,
    )


async def counts(
    session: AsyncSession, ctx: ProjectContext, stage: Stage = "title_abstract"
) -> ScreeningCounts:
    state = await _state(session, ctx, stage)
    ids = await _ids(session, ctx, stage)
    me = ctx.user.id
    decided = sum(1 for i in ids if me in state.decisions.get(i, {}))
    left = sum(
        1
        for i in ids
        if me not in state.decisions.get(i, {})
        and not state.resolutions.get(i)
        and (not state.assigned.get(i) or me in state.assigned[i])
    )
    if not _sees_all(ctx):
        return ScreeningCounts(
            total=len(ids),
            decided_by_me=decided,
            left_for_me=left,
            include=None,
            exclude=None,
            conflict=None,
            pending=None,
            resolved=None,
        )
    statuses = [state.status(i) for i in ids]
    return ScreeningCounts(
        total=len(ids),
        decided_by_me=decided,
        left_for_me=left,
        include=statuses.count("include") + statuses.count("resolved_include"),
        exclude=statuses.count("exclude") + statuses.count("resolved_exclude"),
        conflict=statuses.count("conflict"),
        pending=statuses.count("pending"),
        resolved=statuses.count("resolved_include") + statuses.count("resolved_exclude"),
    )


# ---- Decisions, undo, history --------------------------------------------------------


async def _check_reason(
    session: AsyncSession,
    ctx: ProjectContext,
    stage: Stage,
    decision: str,
    reason_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Full text has no "maybe", and excluding needs a reason of this project."""
    if stage == "title_abstract":
        return None
    if decision == "maybe":
        raise AppError("screening.no_maybe_at_full_text", status_code=422)
    if decision != "exclude":
        return None
    if reason_id is None:
        raise AppError("screening.reason_required", status_code=422)
    reason = (
        await session.scalars(
            select(ExclusionReason).where(
                ExclusionReason.id == reason_id,
                ExclusionReason.project_id == ctx.project.id,
                ExclusionReason.merged_into_id.is_(None),
            )
        )
    ).first()
    if reason is None:
        raise AppError("screening.unknown_reason", status_code=422)
    return reason.id


async def _notify_conflict(
    session: AsyncSession, ctx: ProjectContext, ref_id: uuid.UUID, stage: Stage
) -> None:
    """Tells the admins once that the screeners of this reference disagree."""
    state = await _state(session, ctx, stage)
    if state.status(ref_id) != "conflict":
        return
    title = await session.scalar(select(Reference.title).where(Reference.id == ref_id))
    await notify(
        session,
        await admins_of(session, ctx.project.id),
        ctx.project.id,
        "screening_conflict",
        f"screening_conflict:{stage}:{ref_id}",
        {"reference_id": str(ref_id), "stage": stage, "title": (title or "")[:200]},
    )


async def decide(
    session: AsyncSession,
    ctx: ProjectContext,
    ref_id: uuid.UUID,
    data: ScreeningDecideIn,
    stage: Stage = "title_abstract",
) -> ScreeningDecisionOut:
    _can_screen(ctx)
    await _reference(session, ctx, ref_id, stage)
    assigned = set(
        await session.scalars(
            select(ScreeningAssignment.user_id).where(
                ScreeningAssignment.reference_id == ref_id, ScreeningAssignment.stage == stage
            )
        )
    )
    if assigned and ctx.user.id not in assigned and not ctx.is_admin:
        raise AppError("screening.not_assigned", status_code=403)
    reason_id = await _check_reason(session, ctx, stage, data.decision, data.exclusion_reason_id)
    now = datetime.now(UTC)
    await session.execute(
        update(ScreeningDecision)
        .where(
            ScreeningDecision.reference_id == ref_id,
            ScreeningDecision.user_id == ctx.user.id,
            ScreeningDecision.stage == stage,
            ScreeningDecision.superseded_at.is_(None),
        )
        .values(superseded_at=now)
        .execution_options(synchronize_session=False)
    )
    row = ScreeningDecision(
        project_id=ctx.project.id,
        reference_id=ref_id,
        user_id=ctx.user.id,
        stage=stage,
        decision=data.decision,
        note=(data.note or "").strip() or None,
        exclusion_reason_id=reason_id,
        created_by=ctx.user.id,
    )
    session.add(row)
    await session.flush()
    await _notify_conflict(session, ctx, ref_id, stage)
    await session.commit()
    await session.refresh(row)
    return _decision_out(row)


async def undo(
    session: AsyncSession, ctx: ProjectContext, stage: Stage = "title_abstract"
) -> ScreeningDecisionOut | None:
    """Withdraws my latest decision; my previous decision on that reference comes back.
    Returns the decision now current for that reference (None when there was none)."""
    _can_screen(ctx)
    latest = (
        await session.scalars(
            select(ScreeningDecision)
            .where(
                ScreeningDecision.project_id == ctx.project.id,
                ScreeningDecision.user_id == ctx.user.id,
                ScreeningDecision.stage == stage,
                ScreeningDecision.superseded_at.is_(None),
            )
            .order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
            .limit(1)
        )
    ).first()
    if latest is None:
        raise AppError("screening.nothing_to_undo", status_code=409)
    now = datetime.now(UTC)
    latest.superseded_at = now
    latest.undone = True
    previous = (
        await session.scalars(
            select(ScreeningDecision)
            .where(
                ScreeningDecision.reference_id == latest.reference_id,
                ScreeningDecision.user_id == ctx.user.id,
                ScreeningDecision.stage == stage,
                ScreeningDecision.undone.is_(False),
                ScreeningDecision.id != latest.id,
            )
            .order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
            .limit(1)
        )
    ).first()
    if previous is not None:
        previous.superseded_at = None
    reference_id = latest.reference_id
    await session.commit()
    if previous is None:
        return ScreeningDecisionOut(
            id=latest.id,
            reference_id=reference_id,
            user_id=ctx.user.id,
            decision="none",
            note=None,
            created_at=latest.created_at,
            current=False,
            undone=True,
        )
    await session.refresh(previous)
    return _decision_out(previous)


async def history(
    session: AsyncSession, ctx: ProjectContext, ref_id: uuid.UUID, stage: Stage = "title_abstract"
) -> list[ScreeningDecisionOut]:
    await _reference(session, ctx, ref_id, stage)
    query = select(ScreeningDecision).where(
        ScreeningDecision.reference_id == ref_id, ScreeningDecision.stage == stage
    )
    if not _sees_all(ctx):
        query = query.where(ScreeningDecision.user_id == ctx.user.id)
    names = await _names(session, ctx)
    rows = await session.scalars(query.order_by(ScreeningDecision.created_at))
    return [_decision_out(d, names) for d in rows]


# ---- Conflicts -----------------------------------------------------------------------


async def resolve(
    session: AsyncSession,
    ctx: ProjectContext,
    ref_id: uuid.UUID,
    data: ScreeningResolveIn,
    stage: Stage = "title_abstract",
) -> dict[str, str]:
    if not ctx.is_admin:
        raise ForbiddenError()
    await _reference(session, ctx, ref_id, stage)
    state = await _state(session, ctx, stage)
    if state.status(ref_id) != "conflict":
        raise AppError("screening.not_a_conflict", status_code=409)
    reason_id = await _check_reason(session, ctx, stage, data.decision, data.exclusion_reason_id)
    session.add(
        ScreeningResolution(
            project_id=ctx.project.id,
            reference_id=ref_id,
            stage=stage,
            decision=data.decision,
            reason=data.reason.strip(),
            exclusion_reason_id=reason_id,
            created_by=ctx.user.id,
        )
    )
    await session.commit()
    return {"status": "resolved_" + data.decision}


async def reopen(
    session: AsyncSession, ctx: ProjectContext, ref_id: uuid.UUID, stage: Stage = "title_abstract"
) -> None:
    """Withdraws the resolution of a conflict (soft delete; it stays in the audit log)."""
    if not ctx.is_admin:
        raise ForbiddenError()
    resolution = (
        await session.scalars(
            select(ScreeningResolution).where(
                ScreeningResolution.project_id == ctx.project.id,
                ScreeningResolution.reference_id == ref_id,
                ScreeningResolution.stage == stage,
            )
        )
    ).first()
    if resolution is None:
        raise NotFoundError()
    resolution.deleted_at = datetime.now(UTC)
    await session.commit()


# ---- Useful as reference -------------------------------------------------------------


async def set_useful(
    session: AsyncSession,
    ctx: ProjectContext,
    ref_id: uuid.UUID,
    data: ScreeningUsefulIn,
    stage: Stage = "title_abstract",
) -> dict[str, bool]:
    _can_screen(ctx)
    ref = await _reference(session, ctx, ref_id, stage)
    ref.useful_as_reference = data.useful
    await session.commit()
    return {"useful_as_reference": data.useful}


# ---- Batches -------------------------------------------------------------------------


async def assign(
    session: AsyncSession,
    ctx: ProjectContext,
    data: ScreeningAssignIn,
    stage: Stage = "title_abstract",
) -> ScreeningAssignmentSummary:
    """Gives the next `count` references to a reviewer: the oldest ones not yet given to
    them and given to fewer than two reviewers (double screening)."""
    if not ctx.is_admin:
        raise ForbiddenError()
    member = (
        await session.scalars(
            select(ProjectMember).where(
                ProjectMember.project_id == ctx.project.id, ProjectMember.user_id == data.user_id
            )
        )
    ).first()
    if member is None or not ({Role.REVIEWER.value, Role.ADMIN.value} & set(member.roles)):
        raise AppError("screening.not_a_reviewer", status_code=422)
    state = await _state(session, ctx, stage)
    ids = await _ids(session, ctx, stage)
    chosen = [
        i
        for i in ids
        if data.user_id not in state.assigned.get(i, set())
        and len(state.assigned.get(i, set())) < REQUIRED
        and not state.resolutions.get(i)
    ][: data.count]
    for ref_id in chosen:
        session.add(
            ScreeningAssignment(
                project_id=ctx.project.id,
                reference_id=ref_id,
                user_id=data.user_id,
                stage=stage,
                created_by=ctx.user.id,
            )
        )
    await session.commit()
    return next(s for s in await assignments(session, ctx, stage) if s.user_id == data.user_id)


async def assignments(
    session: AsyncSession, ctx: ProjectContext, stage: Stage = "title_abstract"
) -> list[ScreeningAssignmentSummary]:
    state = await _state(session, ctx, stage)
    names = await _names(session, ctx)
    per_user: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for ref_id, users in state.assigned.items():
        for uid in users:
            per_user[uid].append(ref_id)
    return [
        ScreeningAssignmentSummary(
            user_id=uid,
            user_name=names.get(uid, ""),
            assigned=len(refs),
            decided=sum(1 for r in refs if uid in state.decisions.get(r, {})),
        )
        for uid, refs in sorted(per_user.items(), key=lambda x: names.get(x[0], ""))
    ]


async def unassign(
    session: AsyncSession, ctx: ProjectContext, user_id: uuid.UUID, stage: Stage = "title_abstract"
) -> None:
    """Takes back the references given to a reviewer that they did not decide yet."""
    if not ctx.is_admin:
        raise ForbiddenError()
    state = await _state(session, ctx, stage)
    now = datetime.now(UTC)
    rows = await session.scalars(
        select(ScreeningAssignment).where(
            ScreeningAssignment.project_id == ctx.project.id,
            ScreeningAssignment.user_id == user_id,
            ScreeningAssignment.stage == stage,
        )
    )
    for a in rows:
        if user_id not in state.decisions.get(a.reference_id, {}):
            a.deleted_at = now
    await session.commit()


# ---- Agreement (kappa, in R) ---------------------------------------------------------


async def agreement(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, stage: Stage = "title_abstract"
) -> list[ScreeningAgreementOut]:
    """Cohen's kappa for every pair of reviewers over the references both decided."""
    state = await _state(session, ctx, stage)
    active = set(await _ids(session, ctx, stage))
    names = await _names(session, ctx)
    pairs: dict[tuple[uuid.UUID, uuid.UUID], tuple[list[str], list[str]]] = {}
    for ref_id, by_user in state.decisions.items():
        if ref_id not in active:
            continue
        users = sorted(by_user)
        for i, a in enumerate(users):
            for b in users[i + 1 :]:
                codes = pairs.setdefault((a, b), ([], []))
                codes[0].append(by_user[a].decision)
                codes[1].append(by_user[b].decision)
    out = []
    for (a, b), (codes_a, codes_b) in pairs.items():
        try:
            response = await stats.kappa(codes_a, codes_b)
        except ServiceUnavailableError:
            raise
        if not response.ok:
            raise AppError("error.stats_failed", status_code=502)
        out.append(
            ScreeningAgreementOut(
                user_a=a,
                user_b=b,
                name_a=names.get(a, ""),
                name_b=names.get(b, ""),
                items=response.result["items"],
                agreement_percent=response.result.get("agreement_percent"),
                kappa=response.result.get("kappa"),
                warnings=list(response.warnings),
            )
        )
    return out
