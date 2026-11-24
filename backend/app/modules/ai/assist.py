"""AI assistance, second part (IA3 to IA6; docs/ia.md 7.15.1; stage 7).

The same safety rules as the first part:
- IA3 (extraction) and IA4 (risk of bias) only point at evidence. Each quote is looked up
  in the PDF text and discarded when it is not there; for IA3 the suggested number must
  also be printed inside its quote. The AI never writes into a form: people type the
  value themselves after reading the page, and mark the suggestion as used or not.
- IA5 (search strategy) suggests terms and a PubMed query for a person to review and run.
- IA6 (draft) writes with placeholders; numbers come from the system (PRISMA counts and
  an analysis computed by R), and any digit the AI wrote itself is flagged.
Every suggestion is stored in ai_suggestions and feeds the accuracy metrics.
"""

import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.ai import AIProvider
from app.integrations.stats_client import StatsClient
from app.modules.ai.gateway import CallResult, call
from app.modules.ai.locate import SuggestionOut, _pdf, out, pick_pages, verify
from app.modules.ai.models import AISuggestion
from app.modules.ai.tutor import facts_of, fill
from app.modules.analysis.run import RunIn, run
from app.modules.pdfs.text import normalize_for_search
from app.modules.prisma.service import counts as prisma_counts
from app.modules.projects.access import ProjectContext
from app.modules.uploads.models import PdfPageText

PROMPTS = Path(__file__).parents[2] / "integrations/ai/prompts"


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text("utf-8")


# ---- Shared: pages of a PDF ------------------------------------------------------------


async def _pages(
    session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID, question: str
) -> tuple[Any, list[PdfPageText], list[PdfPageText]]:
    pdf = await _pdf(session, ctx, pdf_id)
    pages = list(
        await session.scalars(
            select(PdfPageText)
            .where(PdfPageText.stored_file_id == pdf.stored_file_id)
            .order_by(PdfPageText.page)
        )
    )
    if not pages or not any(p.content.strip() for p in pages):
        raise AppError("ai.no_pdf_text", status_code=409)
    return pdf, pages, pick_pages(question, pages)


def _block(chosen: list[PdfPageText]) -> str:
    return "\n\n".join(f"[PAGE {p.page}]\n{p.content[:8000]}" for p in chosen)


def _suggestion(
    ctx: ProjectContext,
    result: CallResult[Any],
    *,
    task: str,
    prompt_version: str,
    target_entity: str,
    target_id: uuid.UUID,
    payload: dict[str, Any],
    quote: str | None = None,
    page: int | None = None,
    verified: bool = True,
) -> AISuggestion:
    return AISuggestion(
        project_id=ctx.project.id,
        task=task,
        target_entity=target_entity,
        target_id=target_id,
        payload=payload,
        quote=quote,
        page=page,
        quote_verified=verified,
        status="suggested" if verified else "discarded",
        prompt_version=prompt_version,
        provider=result.provider,
        model=result.model,
        created_by=ctx.user.id,
    )


async def _store(session: AsyncSession, rows: list[AISuggestion]) -> list[SuggestionOut]:
    for row in rows:
        session.add(row)
    await session.commit()
    kept = [r for r in rows if r.status != "discarded"]
    for row in kept:
        await session.refresh(row)
    return [out(r) for r in kept]


# ---- IA3: extraction -------------------------------------------------------------------

FIELDS = Literal[
    "n", "mean", "sd", "se", "ci_low", "ci_high", "median", "q1", "q3",
    "min", "max", "events", "total", "p_value", "t_stat",
]  # fmt: skip
NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


class ExtractIn(BaseModel):
    pdf_id: uuid.UUID
    request: str = Field(min_length=3, max_length=500)  # e.g. "mean and SD of IQ, group < 5"


class ExtractValue(BaseModel):
    field: FIELDS
    value: str = Field(max_length=40)
    quote: str = Field(max_length=2000)
    page: int = Field(ge=1)


class ExtractAnswer(BaseModel):
    values: list[ExtractValue] = Field(max_length=20)
    dispersion_warning: str | None = Field(default=None, max_length=500)


class ExtractOut(BaseModel):
    suggestions: list[SuggestionOut]
    discarded: int
    dispersion_warning: str | None


def number_in_quote(value: str, quote: str) -> bool:
    """The suggested number must be printed in its own quote (comma or point)."""
    wanted = value.strip().replace(",", ".")
    if not NUMBER.fullmatch(wanted):
        return False
    return any(n.replace(",", ".") == wanted for n in NUMBER.findall(quote))


async def extract(
    session: AsyncSession, ctx: ProjectContext, provider: AIProvider, data: ExtractIn
) -> ExtractOut:
    pdf, pages, chosen = await _pages(session, ctx, data.pdf_id, data.request)
    version = "extract-v1"
    result = await call(
        session,
        ctx,
        provider,
        function="extract",
        prompt_version=version,
        system=_prompt(version),
        prompt=f"REQUEST:\n<<<\n{data.request}\n>>>\n\nPAGES:\n<<<\n{_block(chosen)}\n>>>",
        schema=ExtractAnswer,
    )
    texts = {p.page: normalize_for_search(p.content) for p in pages}
    rows = []
    for v in result.answer.values:
        page = verify(v.quote, v.page, texts)
        ok = page is not None and number_in_quote(v.value, v.quote)
        rows.append(
            _suggestion(
                ctx,
                result,
                task="extract",
                prompt_version=version,
                target_entity="pdf",
                target_id=pdf.id,
                payload={"question": data.request, "field": v.field, "value": v.value},
                quote=v.quote,
                page=page or v.page,
                verified=ok,
            )
        )
    kept = await _store(session, rows)
    return ExtractOut(
        suggestions=kept,
        discarded=len(rows) - len(kept),
        dispersion_warning=result.answer.dispersion_warning,
    )


# ---- IA4: risk of bias second opinion -------------------------------------------------


class RobHintIn(BaseModel):
    pdf_id: uuid.UUID
    question: str = Field(min_length=5, max_length=1000)  # the signalling question
    options: list[str] = Field(min_length=2, max_length=10)  # allowed answers


class RobHintAnswer(BaseModel):
    answer: str = Field(max_length=60)
    quote: str = Field(default="", max_length=2000)
    page: int | None = None
    reason: str = Field(max_length=500)


class RobHintOut(BaseModel):
    suggestion: SuggestionOut | None
    discarded: bool
    reason: str | None


async def rob_hint(
    session: AsyncSession, ctx: ProjectContext, provider: AIProvider, data: RobHintIn
) -> RobHintOut:
    pdf, pages, chosen = await _pages(session, ctx, data.pdf_id, data.question)
    version = "rob-v1"
    result = await call(
        session,
        ctx,
        provider,
        function="rob",
        prompt_version=version,
        system=_prompt(version),
        prompt=(
            f"QUESTION:\n<<<\n{data.question}\n>>>\nOPTIONS: {', '.join(data.options)}\n\n"
            f"PAGES:\n<<<\n{_block(chosen)}\n>>>"
        ),
        schema=RobHintAnswer,
    )
    a = result.answer
    texts = {p.page: normalize_for_search(p.content) for p in pages}
    page = verify(a.quote, a.page or 1, texts) if a.quote else None
    # Allowed answer, and either a real quote or no quote at all ("no information").
    ok = a.answer in data.options and (page is not None or not a.quote.strip())
    row = _suggestion(
        ctx,
        result,
        task="rob",
        prompt_version=version,
        target_entity="pdf",
        target_id=pdf.id,
        payload={"question": data.question, "answer": a.answer, "reason": a.reason},
        quote=a.quote or None,
        page=page,
        verified=ok,
    )
    kept = await _store(session, [row])
    return RobHintOut(suggestion=kept[0] if kept else None, discarded=not kept, reason=a.reason)


# ---- IA5: search strategy -------------------------------------------------------------


class Concept(BaseModel):
    concept: str = Field(max_length=200)
    mesh: list[str] = Field(default_factory=list, max_length=20)
    decs: list[str] = Field(default_factory=list, max_length=20)
    free_text: list[str] = Field(default_factory=list, max_length=30)


class SearchAnswer(BaseModel):
    concepts: list[Concept] = Field(max_length=8)
    pubmed: str = Field(max_length=4000)


class SearchHelpOut(BaseModel):
    suggestion: SuggestionOut
    concepts: list[Concept]
    pubmed: str


async def search_help(
    session: AsyncSession, ctx: ProjectContext, provider: AIProvider
) -> SearchHelpOut:
    project = ctx.project
    if not (project.question or project.pico):
        raise AppError("ai.no_question", status_code=409)
    pico = "\n".join(f"- {k}: {v}" for k, v in (project.pico or {}).items() if v)
    version = "search-v1"
    result = await call(
        session,
        ctx,
        provider,
        function="search",
        prompt_version=version,
        system=_prompt(version),
        prompt=f"QUESTION:\n<<<\n{project.question or ''}\n>>>\nPICO:\n<<<\n{pico}\n>>>",
        schema=SearchAnswer,
    )
    row = _suggestion(
        ctx,
        result,
        task="search",
        prompt_version=version,
        target_entity="project",
        target_id=project.id,
        payload={"question": "search strategy", **result.answer.model_dump()},
    )
    kept = await _store(session, [row])
    return SearchHelpOut(
        suggestion=kept[0], concepts=result.answer.concepts, pubmed=result.answer.pubmed
    )


# ---- IA6: draft of Methods and Results --------------------------------------------------


class DraftIn(BaseModel):
    lang: Literal["pt-BR", "en"] = "pt-BR"
    analysis: RunIn | None = None


class DraftAnswer(BaseModel):
    methods: str = Field(max_length=6000)
    results: str = Field(max_length=6000)


class DraftOut(BaseModel):
    methods: str
    results: str
    unverified: list[str]
    suggestion: SuggestionOut


async def draft(
    session: AsyncSession,
    ctx: ProjectContext,
    stats: StatsClient,
    provider: AIProvider,
    data: DraftIn,
) -> DraftOut:
    flow = await prisma_counts(session, ctx)
    facts: dict[str, str] = {k: str(v) for k, v in flow.values.items()}
    for db in flow.identified:
        facts[f"records_{re.sub(r'[^a-z0-9]+', '_', db.database.lower()).strip('_')}"] = str(db.n)
    context = "Databases: " + (", ".join(d.database for d in flow.identified) or "(none)") + ".\n"
    if data.analysis is not None:
        main = await run(session, ctx, stats, data.analysis)
        facts |= facts_of(main.result, main.assembly.measure, data.lang)
        context += (
            f"Main analysis: outcome {main.assembly.outcome_name} ({main.assembly.timepoint}), "
            f"measure {main.assembly.measure}, model {main.method}, test {main.test}.\n"
        )
    listed = "\n".join(f"- {{{{{k}}}}}" for k in facts) or "(none)"
    version = "draft-v1"
    result = await call(
        session,
        ctx,
        provider,
        function="draft",
        prompt_version=version,
        system=_prompt(version),
        prompt=f"LANGUAGE: {data.lang}\nCONTEXT:\n{context}\nFACTS:\n{listed}",
        schema=DraftAnswer,
    )
    methods, flags_m, _ = fill(result.answer.methods, facts)
    results, flags_r, _ = fill(result.answer.results, facts)
    unverified = list(dict.fromkeys([*flags_m, *flags_r]))
    row = _suggestion(
        ctx,
        result,
        task="draft",
        prompt_version=version,
        target_entity="project",
        target_id=ctx.project.id,
        payload={"question": "draft", "unverified": len(unverified)},
    )
    kept = await _store(session, [row])
    return DraftOut(methods=methods, results=results, unverified=unverified, suggestion=kept[0])
