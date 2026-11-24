"""Passage finder (IA2; docs/ia.md 7.15.1 and 7.15.3 rule 1; stage 7 step 5).

"Where does the article talk about blinding?" -> page and exact passage. The person
reads and decides; nothing becomes data.

- Minimal context: only the pages that share the most words with the question (up to
  three, each cut to a size limit) are sent, never the whole PDF.
- Verified quotation: every passage the AI returns is looked up in the text extracted
  from the PDF (normalised: case, accents, line breaks and hyphenation). A passage that
  is not there is discarded and recorded as a failure; one found on another page is
  kept with the right page.
- Every suggestion is stored (suggested or discarded) with prompt version, provider and
  model; people mark it useful or not, which feeds the accuracy metrics (step 6).
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.integrations.ai import AIProvider
from app.modules.ai import metrics
from app.modules.ai.gateway import call
from app.modules.ai.models import AISuggestion
from app.modules.pdfs.models import PdfFile
from app.modules.pdfs.text import normalize_for_search
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.uploads.models import PdfPageText

PROMPT_VERSION = "locate-v1"
SYSTEM = (Path(__file__).parents[2] / "integrations/ai/prompts/locate-v1.md").read_text("utf-8")
MAX_PAGES = 3
MAX_PAGE_CHARS = 8000
WORD = re.compile(r"[a-z0-9]{3,}")
DECIDERS = {Role.ADMIN, Role.REVIEWER, Role.EXTRACTOR, Role.STATISTICIAN}


class LocateIn(BaseModel):
    pdf_id: uuid.UUID
    question: str = Field(min_length=3, max_length=500)


class Passage(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)


class LocateAnswer(BaseModel):
    passages: list[Passage] = Field(max_length=3)


class SuggestionOut(BaseModel):
    id: uuid.UUID
    task: str
    target_id: uuid.UUID
    question: str | None
    payload: dict[str, Any]  # what was suggested (e.g. field and value), never data
    quote: str | None
    page: int | None
    quote_verified: bool
    status: str
    prompt_version: str
    provider: str
    model: str
    created_at: datetime


class LocateOut(BaseModel):
    suggestions: list[SuggestionOut]  # verified passages only
    discarded: int  # passages not found in the PDF text
    pages_sent: list[int]
    cached: bool


class DecisionIn(BaseModel):
    status: Literal["accepted", "rejected"]


def _words(text: str) -> set[str]:
    return set(WORD.findall(normalize_for_search(text)))


def pick_pages(question: str, pages: list[PdfPageText]) -> list[PdfPageText]:
    """Pages sharing most words with the question (ties: earlier page)."""
    wanted = _words(question)
    scored = sorted(pages, key=lambda p: (-len(wanted & _words(p.content)), p.page))
    return sorted(scored[:MAX_PAGES], key=lambda p: p.page)


def verify(quote: str, page: int, pages: dict[int, str]) -> int | None:
    """Page where the quote really is (the stated one first), or None."""
    needle = normalize_for_search(quote)
    if len(needle) < 10:
        return None
    if needle in pages.get(page, ""):
        return page
    for number, text in pages.items():
        if needle in text:
            return number
    return None


def out(s: AISuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=s.id,
        task=s.task,
        target_id=s.target_id,
        question=(s.payload or {}).get("question"),
        payload=dict(s.payload or {}),
        quote=s.quote,
        page=s.page,
        quote_verified=s.quote_verified,
        status=s.status,
        prompt_version=s.prompt_version,
        provider=s.provider,
        model=s.model,
        created_at=s.created_at,
    )


async def _pdf(session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID) -> PdfFile:
    pdf = (
        await session.scalars(
            select(PdfFile).where(PdfFile.id == pdf_id, PdfFile.project_id == ctx.project.id)
        )
    ).first()
    if pdf is None:
        raise NotFoundError()
    return pdf


async def locate(
    session: AsyncSession, ctx: ProjectContext, provider: AIProvider, data: LocateIn
) -> LocateOut:
    pdf = await _pdf(session, ctx, data.pdf_id)
    pages = list(
        await session.scalars(
            select(PdfPageText)
            .where(PdfPageText.stored_file_id == pdf.stored_file_id)
            .order_by(PdfPageText.page)
        )
    )
    if not pages or not any(p.content.strip() for p in pages):
        raise AppError("ai.no_pdf_text", status_code=409)
    chosen = pick_pages(data.question, pages)
    block = "\n\n".join(f"[PAGE {p.page}]\n{p.content[:MAX_PAGE_CHARS]}" for p in chosen)
    prompt = f"QUESTION:\n<<<\n{data.question}\n>>>\n\nPAGES:\n<<<\n{block}\n>>>"
    result = await call(
        session,
        ctx,
        provider,
        function="locate",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM,
        prompt=prompt,
        schema=LocateAnswer,
    )
    texts = {p.page: normalize_for_search(p.content) for p in pages}
    kept: list[AISuggestion] = []
    discarded = 0
    for passage in result.answer.passages:
        page = verify(passage.quote, passage.page, texts)
        row = AISuggestion(
            project_id=ctx.project.id,
            task="locate",
            target_entity="pdf",
            target_id=pdf.id,
            payload={"question": data.question, "pages_sent": [p.page for p in chosen]},
            quote=passage.quote,
            page=page or passage.page,
            quote_verified=page is not None,
            status="suggested" if page is not None else "discarded",
            prompt_version=PROMPT_VERSION,
            provider=result.provider,
            model=result.model,
            created_by=ctx.user.id,
        )
        session.add(row)
        if page is None:
            discarded += 1
        else:
            kept.append(row)
    await session.commit()
    for row in kept:
        await session.refresh(row)
    return LocateOut(
        suggestions=[out(s) for s in kept],
        discarded=discarded,
        pages_sent=[p.page for p in chosen],
        cached=result.cached,
    )


async def suggestions(
    session: AsyncSession, ctx: ProjectContext, target_id: uuid.UUID
) -> list[SuggestionOut]:
    rows = await session.scalars(
        select(AISuggestion)
        .where(
            AISuggestion.project_id == ctx.project.id,
            AISuggestion.target_id == target_id,
            AISuggestion.status != "discarded",
        )
        .order_by(AISuggestion.created_at.desc())
    )
    return [out(s) for s in rows]


async def decide(
    session: AsyncSession, ctx: ProjectContext, suggestion_id: uuid.UUID, data: DecisionIn
) -> SuggestionOut:
    if not (DECIDERS & ctx.roles):
        raise ForbiddenError()
    row = (
        await session.scalars(
            select(AISuggestion).where(
                AISuggestion.id == suggestion_id, AISuggestion.project_id == ctx.project.id
            )
        )
    ).first()
    if row is None or row.status == "discarded":
        raise NotFoundError()
    row.status = data.status
    row.decided_by = ctx.user.id
    row.decided_at = datetime.now(UTC)
    await session.flush()
    await metrics.check(session, ctx, row.task)
    await session.commit()
    await session.refresh(row)
    return out(row)
