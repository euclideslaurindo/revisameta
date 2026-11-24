"""Measured accuracy of the AI against people (docs/ia.md 7.15.4; stage 7 step 6).

For every task, the latest suggestions that a person decided (accepted, corrected or
rejected) give the hit rate: accepted / decided. Suggestions the system discarded (a
quote that is not in the PDF) are counted apart as failures.

Approved rule: when at least `ai_accuracy_min_decided` (10) of the last
`ai_accuracy_window` (30) decided suggestions exist and the hit rate falls below
`ai_min_accuracy` (80%), the function is switched off in the project, the admins get a
notice, and an admin may turn it back on in the settings.

The same numbers feed the AI-use statement for the manuscript (7.15.6).
"""

import io
from datetime import UTC, datetime
from typing import Any, Literal

from docx import Document
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai.models import AISettings, AISuggestion
from app.modules.ai.settings import FUNCTIONS
from app.modules.exports.extraction import _slug
from app.modules.notifications.service import admins_of, notify
from app.modules.projects.access import ProjectContext

DECIDED = ("accepted", "corrected", "rejected")


class TaskMetrics(BaseModel):
    task: str
    window: int  # how many decided suggestions were looked at (the latest ones)
    decided: int
    accepted: int
    corrected: int
    rejected: int
    discarded: int  # thrown away by the system (all time)
    accuracy: float | None  # accepted / decided in the window; None below the minimum
    threshold: float
    min_decided: int
    disabled: bool
    prompt_versions: list[str]
    models: list[str]


class MetricsOut(BaseModel):
    tasks: list[TaskMetrics]


async def task_metrics(session: AsyncSession, project_id: object, task: str) -> TaskMetrics:
    settings = get_settings()
    latest = list(
        await session.scalars(
            select(AISuggestion.status)
            .where(
                AISuggestion.project_id == project_id,
                AISuggestion.task == task,
                AISuggestion.status.in_(DECIDED),
            )
            .order_by(AISuggestion.decided_at.desc())
            .limit(settings.ai_accuracy_window)
        )
    )
    discarded = await session.scalar(
        select(func.count())
        .select_from(AISuggestion)
        .where(
            AISuggestion.project_id == project_id,
            AISuggestion.task == task,
            AISuggestion.status == "discarded",
        )
    )
    used = await session.execute(
        select(AISuggestion.prompt_version, AISuggestion.model)
        .where(AISuggestion.project_id == project_id, AISuggestion.task == task)
        .distinct()
    )
    pairs = used.all()
    row = (
        await session.scalars(select(AISettings).where(AISettings.project_id == project_id))
    ).first()
    decided = len(latest)
    accepted = latest.count("accepted")
    return TaskMetrics(
        task=task,
        window=settings.ai_accuracy_window,
        decided=decided,
        accepted=accepted,
        corrected=latest.count("corrected"),
        rejected=latest.count("rejected"),
        discarded=discarded or 0,
        accuracy=accepted / decided if decided >= settings.ai_accuracy_min_decided else None,
        threshold=settings.ai_min_accuracy,
        min_decided=settings.ai_accuracy_min_decided,
        disabled=bool(row and task in (row.disabled_functions or {})),
        prompt_versions=sorted({p for p, _ in pairs}),
        models=sorted({m for _, m in pairs}),
    )


async def metrics(session: AsyncSession, ctx: ProjectContext) -> MetricsOut:
    return MetricsOut(tasks=[await task_metrics(session, ctx.project.id, t) for t in FUNCTIONS])


async def check(session: AsyncSession, ctx: ProjectContext, task: str) -> bool:
    """After a decision: switches the function off when accuracy fell below the threshold.
    Returns True when it was switched off now. The caller commits."""
    m = await task_metrics(session, ctx.project.id, task)
    if m.accuracy is None or m.accuracy >= m.threshold or m.disabled:
        return False
    row = (
        await session.scalars(select(AISettings).where(AISettings.project_id == ctx.project.id))
    ).first()
    if row is None:
        return False
    row.disabled_functions = {
        **(row.disabled_functions or {}),
        task: datetime.now(UTC).isoformat(),
    }
    await notify(
        session,
        await admins_of(session, ctx.project.id),
        ctx.project.id,
        "ai_disabled",
        f"ai_disabled:{task}:{row.disabled_functions[task]}",
        {"task": task, "accuracy": round(m.accuracy * 100), "threshold": round(m.threshold * 100)},
    )
    return True


TEXTS: dict[str, dict[str, Any]] = {
    "pt-BR": {
        "title": "Declaração de uso de inteligência artificial",
        "intro": (
            "Esta revisão usou o RevisaMeta. As funções de IA abaixo só explicaram "
            "resultados ou apontaram trechos dos artigos; nenhuma calculou estatística, "
            "decidiu inclusão ou julgou risco de viés, e nenhuma sugestão virou dado sem "
            "confirmação de uma pessoa. Toda citação sugerida foi conferida "
            "automaticamente no texto do PDF."
        ),
        "task": {
            "tutor": "Tutor (explicação de conceitos e resultados)",
            "locate": "Localizador de trechos nos PDFs",
            "extract": "Extração assistida (valores com citação conferida)",
            "rob": "Segunda opinião em risco de viés",
            "search": "Ajuda na estratégia de busca",
            "draft": "Rascunho de Métodos e Resultados",
        },
        "unused": "Nenhuma função de IA foi usada neste projeto.",
        "line": (
            "{task}: provedor e modelo {models}; versões de prompt {versions}; "
            "{decided} sugestões avaliadas por pessoas nas últimas {window}, "
            "{accepted} aceitas, {corrected} corrigidas, {rejected} rejeitadas; "
            "{discarded} descartadas pelo sistema por citação inexistente."
        ),
        "accuracy": " Taxa de acerto: {accuracy}%.",
        "file": "declaracao-uso-ia",
    },
    "en": {
        "title": "Statement on the use of artificial intelligence",
        "intro": (
            "This review used RevisaMeta. The AI features below only explained results or "
            "pointed at passages of the articles; none computed statistics, decided "
            "inclusion or judged risk of bias, and no suggestion became data without a "
            "person's confirmation. Every suggested quotation was checked automatically "
            "against the PDF text."
        ),
        "task": {
            "tutor": "Tutor (explaining concepts and results)",
            "locate": "Passage finder in the PDFs",
            "extract": "Assisted extraction (values with checked quotes)",
            "rob": "Risk of bias second opinion",
            "search": "Search strategy help",
            "draft": "Draft of Methods and Results",
        },
        "unused": "No AI feature was used in this project.",
        "line": (
            "{task}: provider and model {models}; prompt versions {versions}; "
            "{decided} suggestions reviewed by people in the latest {window}, "
            "{accepted} accepted, {corrected} corrected, {rejected} rejected; "
            "{discarded} discarded by the system for a non-existent quotation."
        ),
        "accuracy": " Accuracy: {accuracy}%.",
        "file": "ai-use-statement",
    },
}


async def statement(
    session: AsyncSession, ctx: ProjectContext, lang: Literal["pt-BR", "en"]
) -> tuple[bytes, str]:
    t = TEXTS[lang]
    data = await metrics(session, ctx)
    doc = Document()
    doc.add_heading(t["title"], level=1)
    doc.add_paragraph(t["intro"])
    used = [m for m in data.tasks if m.prompt_versions]
    if not used:
        doc.add_paragraph(t["unused"])
    for m in used:
        text = t["line"].format(
            task=t["task"][m.task],
            models=", ".join(m.models),
            versions=", ".join(m.prompt_versions),
            decided=m.decided,
            window=m.window,
            accepted=m.accepted,
            corrected=m.corrected,
            rejected=m.rejected,
            discarded=m.discarded,
        )
        if m.accuracy is not None:
            text += t["accuracy"].format(accuracy=round(m.accuracy * 100))
        doc.add_paragraph(text, style="List Bullet")
    buffer = io.BytesIO()
    doc.save(buffer)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return buffer.getvalue(), f"{_slug(ctx.project.title)}_{t['file']}_{day}.docx"
