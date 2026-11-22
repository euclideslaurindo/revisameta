"""Screening prioritization with classic machine learning (docs/modulos.md 7.3; stage 5 step 5).

Like ASReview: after some decisions, a TF-IDF + logistic regression model, trained on the
project's own title and abstract decisions, puts the references most likely to be
included first. Local and free (scikit-learn), no language model.

It only changes the ORDER of the list. It never excludes, never decides and never hides
a reference: every reference still has to be read, unless the protocol defines a
stopping rule (the screen says so).

Labels: a reference counts as "include" when any reviewer chose include or maybe, and
as "exclude" when every decision so far is exclude. The model needs at least
MIN_EACH of each before it is trained.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ForbiddenError
from app.db.base import new_id
from app.integrations.queue import JobQueue
from app.modules.jobs.models import BackgroundJob, JobStatus
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Project
from app.modules.screening.models import ScreeningDecision
from app.modules.screening.service import SCREENERS
from app.modules.studies.models import Reference

MIN_EACH = 5
BATCH = 1000


class PriorityInfo(BaseModel):
    trained_at: datetime | None
    includes: int  # labelled references used to train
    excludes: int
    scored: int
    min_each: int = MIN_EACH
    job_id: uuid.UUID | None = None


def info_of(project: Project) -> PriorityInfo:
    data: dict[str, Any] = (project.screening_settings or {}).get("priority") or {}
    return PriorityInfo(
        trained_at=data.get("trained_at"),
        includes=data.get("includes", 0),
        excludes=data.get("excludes", 0),
        scored=data.get("scored", 0),
    )


def rank(texts: dict[uuid.UUID, str], labels: dict[uuid.UUID, int]) -> dict[uuid.UUID, float]:
    """Probability of inclusion for every reference, from the labelled ones. Pure."""
    ids = list(texts)
    vectorizer = TfidfVectorizer(
        sublinear_tf=True,
        ngram_range=(1, 2),
        min_df=1,
        max_features=50_000,
        strip_accents="unicode",
    )
    matrix = vectorizer.fit_transform([texts[i] for i in ids])
    labelled = [n for n, i in enumerate(ids) if i in labels]
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(matrix[labelled], [labels[ids[n]] for n in labelled])
    scores = model.predict_proba(matrix)[:, 1]
    return {i: float(s) for i, s in zip(ids, scores, strict=True)}


async def start(session: AsyncSession, ctx: ProjectContext, queue: JobQueue) -> PriorityInfo:
    if not (SCREENERS & ctx.roles):
        raise ForbiddenError()
    job = BackgroundJob(
        id=new_id(), project_id=ctx.project.id, kind="screening_priority", created_by=ctx.user.id
    )
    session.add(job)
    await session.commit()
    await queue.enqueue(
        "screening_priority_task", project_id=str(ctx.project.id), job_id=str(job.id)
    )
    await session.refresh(ctx.project)
    out = info_of(ctx.project)
    out.job_id = job.id
    return out


async def _set_job(
    maker: async_sessionmaker[AsyncSession], job_id: uuid.UUID, **values: Any
) -> None:
    async with maker() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is not None:
            for key, value in values.items():
                setattr(job, key, value)
            await session.commit()


async def train(
    maker: async_sessionmaker[AsyncSession], project_id: uuid.UUID, job_id: uuid.UUID
) -> None:
    """Worker task: trains on the current decisions and stores a score per reference."""
    await _set_job(maker, job_id, status=JobStatus.RUNNING, progress=5)
    async with maker() as session:
        rows = (
            await session.execute(
                select(Reference.id, Reference.title, Reference.abstract, Reference.keywords).where(
                    Reference.project_id == project_id,
                    Reference.search_id.is_not(None),
                    Reference.duplicate_of.is_(None),
                )
            )
        ).all()
        decisions = (
            await session.execute(
                select(ScreeningDecision.reference_id, ScreeningDecision.decision).where(
                    ScreeningDecision.project_id == project_id,
                    ScreeningDecision.stage == "title_abstract",
                    ScreeningDecision.superseded_at.is_(None),
                )
            )
        ).all()
    texts = {r[0]: " ".join(x for x in r[1:] if x) for r in rows}
    seen: dict[uuid.UUID, set[str]] = {}
    for ref_id, decision in decisions:
        if ref_id in texts:
            seen.setdefault(ref_id, set()).add(decision)
    labels = {ref_id: 0 if kinds == {"exclude"} else 1 for ref_id, kinds in seen.items()}
    includes = sum(labels.values())
    excludes = len(labels) - includes
    if includes < MIN_EACH or excludes < MIN_EACH:
        await _set_job(
            maker,
            job_id,
            status=JobStatus.FAILED,
            error_code="screening.priority_needs_decisions",
            result={"includes": includes, "excludes": excludes, "min_each": MIN_EACH},
        )
        return
    await _set_job(maker, job_id, progress=30)
    scores = rank(texts, labels)
    await _set_job(maker, job_id, progress=70)
    items = list(scores.items())
    async with maker() as session:
        for start_at in range(0, len(items), BATCH):
            chunk = items[start_at : start_at + BATCH]
            for ref_id, score in chunk:
                await session.execute(
                    update(Reference)
                    .where(Reference.id == ref_id)
                    .values(priority_score=score)
                    .execution_options(synchronize_session=False)
                )
            await session.commit()
        project = await session.get(Project, project_id)
        if project is not None:
            settings = dict(project.screening_settings or {})
            settings["priority"] = {
                "trained_at": datetime.now(UTC).isoformat(),
                "includes": includes,
                "excludes": excludes,
                "scored": len(scores),
            }
            project.screening_settings = settings
            await session.commit()
    await _set_job(
        maker,
        job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        result={"includes": includes, "excludes": excludes, "scored": len(scores)},
    )
