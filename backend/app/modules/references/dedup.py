"""Deduplication of imported references (docs/modulos.md 7.2; stage 5 step 2).

- run: finds the pairs with the rules of dedup_rules. Pairs a person already decided
  are kept as they are; pending pairs no longer found are dropped.
- confirm: a person says which record stays; the other points to it (duplicate_of)
  and leaves the screening. Nothing is erased and it can be undone.
- reject: "not a duplicate". Related pairs can only be acknowledged, never confirmed.
- report: counts for the PRISMA flow diagram and a CSV for the Methods section.
"""

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.references.dedup_rules import DedupSettings, blocks, candidate, compare
from app.modules.references.models import DuplicatePair
from app.modules.references.service import SearchReferenceOut
from app.modules.studies.models import Reference

DECIDERS = {Role.ADMIN, Role.REVIEWER}


class DuplicatePairOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    score: float
    criteria: dict[str, Any]
    kept_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    version: int
    a: SearchReferenceOut
    b: SearchReferenceOut


class DedupRunOut(BaseModel):
    certain: int
    probable: int
    related: int
    new_pairs: int


class DedupDecideIn(BaseModel):
    action: Literal["confirm", "reject", "undo"]
    keep: Literal["a", "b"] | None = None  # for confirm
    version: int


class DedupReportOut(BaseModel):
    imported: int  # references from searches (not removed with their search)
    duplicates_removed: int  # confirmed by a person
    after_duplicates: int  # what goes to screening
    pending: dict[str, int]  # pairs still waiting, per kind
    rejected: int


def settings_of(ctx: ProjectContext) -> DedupSettings:
    return DedupSettings.model_validate(ctx.project.dedup_settings or {})


def _can_decide(ctx: ProjectContext) -> None:
    if not (DECIDERS & ctx.roles):
        raise ForbiddenError()


async def update_settings(
    session: AsyncSession, ctx: ProjectContext, data: DedupSettings
) -> DedupSettings:
    if not ctx.is_admin:
        raise ForbiddenError()
    ctx.project.dedup_settings = data.model_dump()
    await session.commit()
    return data


def _imported(ctx: ProjectContext) -> list[Any]:
    return [Reference.project_id == ctx.project.id, Reference.search_id.is_not(None)]


async def run(session: AsyncSession, ctx: ProjectContext) -> DedupRunOut:
    _can_decide(ctx)
    settings = settings_of(ctx)
    rows = (
        await session.execute(
            select(
                Reference.id,
                Reference.title,
                Reference.authors,
                Reference.year,
                Reference.journal,
                Reference.volume,
                Reference.pages,
                Reference.doi,
                Reference.pmid,
            ).where(*_imported(ctx))
        )
    ).all()
    items = [candidate(*row) for row in rows]
    found: dict[tuple[uuid.UUID, uuid.UUID], tuple[str, dict[str, Any], float]] = {}
    for group in blocks(items).values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                if key in found:
                    continue
                result = compare(a, b, settings)
                if result is not None:
                    found[key] = result
    existing = {
        (p.reference_a_id, p.reference_b_id): p
        for p in await session.scalars(
            select(DuplicatePair).where(DuplicatePair.project_id == ctx.project.id)
        )
    }
    new = 0
    for key, (kind, criteria, score) in found.items():
        pair = existing.pop(key, None)
        if pair is None:
            session.add(
                DuplicatePair(
                    project_id=ctx.project.id,
                    reference_a_id=key[0],
                    reference_b_id=key[1],
                    kind=kind,
                    criteria=criteria,
                    score=score,
                    created_by=ctx.user.id,
                )
            )
            new += 1
        elif pair.status == "pending":
            pair.kind, pair.criteria, pair.score = kind, criteria, score
    now = datetime.now(UTC)
    for pair in existing.values():
        if pair.status == "pending":
            pair.deleted_at = now  # no longer found (e.g. thresholds changed)
    await session.commit()
    kinds = [k for k, _, _ in found.values()]
    return DedupRunOut(
        certain=kinds.count("certain"),
        probable=kinds.count("probable"),
        related=kinds.count("related"),
        new_pairs=new,
    )


async def _references(
    session: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, SearchReferenceOut]:
    if not ids:
        return {}
    rows = await session.scalars(select(Reference).where(Reference.id.in_(ids)))
    return {r.id: SearchReferenceOut.model_validate(r, from_attributes=True) for r in rows}


async def list_pairs(
    session: AsyncSession, ctx: ProjectContext, kind: str | None, status: str | None
) -> list[DuplicatePairOut]:
    query = select(DuplicatePair).where(DuplicatePair.project_id == ctx.project.id)
    if kind:
        query = query.where(DuplicatePair.kind == kind)
    if status:
        query = query.where(DuplicatePair.status == status)
    pairs = list(await session.scalars(query.order_by(DuplicatePair.score.desc())))
    refs = await _references(
        session, {p.reference_a_id for p in pairs} | {p.reference_b_id for p in pairs}
    )
    out = []
    for p in pairs:
        a, b = refs.get(p.reference_a_id), refs.get(p.reference_b_id)
        if a is None or b is None:  # a reference removed with its search
            continue
        out.append(
            DuplicatePairOut(
                id=p.id,
                kind=p.kind,
                status=p.status,
                score=p.score,
                criteria=p.criteria,
                kept_id=p.kept_id,
                decided_by=p.decided_by,
                decided_at=p.decided_at,
                version=p.version,
                a=a,
                b=b,
            )
        )
    return out


async def _root(session: AsyncSession, ref_id: uuid.UUID) -> uuid.UUID:
    """The record that finally stays when duplicates chain (A -> B -> C gives C)."""
    seen = {ref_id}
    current = ref_id
    while True:
        parent = await session.scalar(select(Reference.duplicate_of).where(Reference.id == current))
        if parent is None or parent in seen:
            return current
        seen.add(parent)
        current = parent


async def decide(
    session: AsyncSession, ctx: ProjectContext, pair_id: uuid.UUID, data: DedupDecideIn
) -> DuplicatePairOut:
    _can_decide(ctx)
    pair = (
        await session.scalars(
            select(DuplicatePair).where(
                DuplicatePair.id == pair_id, DuplicatePair.project_id == ctx.project.id
            )
        )
    ).first()
    if pair is None:
        raise NotFoundError()
    if pair.version != data.version:
        raise ConflictError()
    now = datetime.now(UTC)
    if data.action == "confirm":
        if pair.kind == "related":
            raise AppError("dedup.related_is_not_duplicate", status_code=409)
        if pair.status != "pending" or data.keep is None:
            raise AppError("dedup.not_pending", status_code=409)
        kept = pair.reference_a_id if data.keep == "a" else pair.reference_b_id
        removed = pair.reference_b_id if data.keep == "a" else pair.reference_a_id
        root = await _root(session, kept)
        if root == removed:
            raise AppError("dedup.cycle", status_code=409)
        ref = await session.get(Reference, removed)
        if ref is None:
            raise NotFoundError()
        ref.duplicate_of = root
        # Records that pointed to the removed one now point to the record that stays.
        await session.execute(
            update(Reference).where(Reference.duplicate_of == removed).values(duplicate_of=root)
        )
        pair.status, pair.kept_id = "confirmed", kept
    elif data.action == "reject":
        if pair.status != "pending":
            raise AppError("dedup.not_pending", status_code=409)
        pair.status = "rejected"
    else:  # undo
        if pair.status == "confirmed" and pair.kept_id is not None:
            removed = (
                pair.reference_b_id if pair.kept_id == pair.reference_a_id else pair.reference_a_id
            )
            ref = await session.get(Reference, removed)
            if ref is not None:
                ref.duplicate_of = None
        pair.status, pair.kept_id = "pending", None
    pair.decided_by = ctx.user.id if data.action != "undo" else None
    pair.decided_at = now if data.action != "undo" else None
    await session.commit()
    return next(p for p in await list_pairs(session, ctx, None, None) if p.id == pair.id)


async def confirm_certain(session: AsyncSession, ctx: ProjectContext) -> int:
    """Confirms every pending certain pair (same DOI or PMID), keeping the older record."""
    _can_decide(ctx)
    pairs = list(
        await session.scalars(
            select(DuplicatePair).where(
                DuplicatePair.project_id == ctx.project.id,
                DuplicatePair.kind == "certain",
                DuplicatePair.status == "pending",
            )
        )
    )
    done = 0
    for pair in pairs:
        # reference_a_id is the smaller UUID v7, that is, the one imported first.
        await decide(
            session, ctx, pair.id, DedupDecideIn(action="confirm", keep="a", version=pair.version)
        )
        done += 1
    return done


async def report(session: AsyncSession, ctx: ProjectContext) -> DedupReportOut:
    imported = (
        await session.scalar(select(func.count()).select_from(Reference).where(*_imported(ctx)))
        or 0
    )
    removed = (
        await session.scalar(
            select(func.count())
            .select_from(Reference)
            .where(*_imported(ctx), Reference.duplicate_of.is_not(None))
        )
        or 0
    )
    rows = (
        await session.execute(
            select(DuplicatePair.kind, DuplicatePair.status, func.count())
            .where(DuplicatePair.project_id == ctx.project.id)
            .group_by(DuplicatePair.kind, DuplicatePair.status)
        )
    ).all()
    pending = {k: n for k, s, n in rows if s == "pending"}
    return DedupReportOut(
        imported=imported,
        duplicates_removed=removed,
        after_duplicates=imported - removed,
        pending={k: pending.get(k, 0) for k in ("certain", "probable", "related")},
        rejected=sum(n for _, s, n in rows if s == "rejected"),
    )


async def report_csv(session: AsyncSession, ctx: ProjectContext) -> str:
    """One line per pair, with the criteria and the decision (for the Methods section)."""
    pairs = await list_pairs(session, ctx, None, None)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "kind",
            "status",
            "title_score",
            "criteria",
            "kept",
            "title_a",
            "year_a",
            "doi_a",
            "title_b",
            "year_b",
            "doi_b",
            "decided_at",
        ]
    )
    for p in pairs:
        kept = "a" if p.kept_id == p.a.id else "b" if p.kept_id == p.b.id else ""
        criteria = "; ".join(f"{k}={v}" for k, v in p.criteria.items())
        writer.writerow(
            [
                p.kind,
                p.status,
                f"{p.score:.4f}",
                criteria,
                kept,
                p.a.title,
                p.a.year or "",
                p.a.doi or "",
                p.b.title,
                p.b.year or "",
                p.b.doi or "",
                p.decided_at.isoformat() if p.decided_at else "",
            ]
        )
    return out.getvalue()
