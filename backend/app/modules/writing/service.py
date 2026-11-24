# ruff: noqa: E501  (bilingual sentence templates read better one per line)
"""Writing support without AI (docs/modulos.md 7.14 and 7.10; stage 8 steps 5 and 6).

- Structured abstract (Background/Objective, Methods, Results, Conclusion) and a draft
  of Methods and Results (DOCX). Fixed sentences filled with the system's own numbers:
  PRISMA counts, the searches, the analysis plan, an analysis computed by R and its
  GRADE certainty. Anything the system does not know stays as a bracketed note for the
  group. The conclusion is always left to the group.
- The abstract the group edits is saved with its word and character limits (the
  congress rules); the screen counts as people type.
"""

import io
from datetime import UTC, date, datetime
from typing import Literal

from docx import Document
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError
from app.integrations.stats_client import StatsClient
from app.modules.ai.tutor import facts_of
from app.modules.analysis.run import RunIn, run
from app.modules.exports.extraction import _slug
from app.modules.grade.models import GradeAssessment
from app.modules.prisma.service import counts as prisma_counts
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.protocol.analysis_plan import current_plan
from app.modules.references.models import Search
from app.modules.writing.models import AbstractDraft

Lang = Literal["pt-BR", "en"]
EDITORS = {Role.ADMIN, Role.REVIEWER, Role.EXTRACTOR, Role.STATISTICIAN}
MODEL = {
    "pt-BR": {
        "REML": "efeitos aleatórios (REML)",
        "DL": "efeitos aleatórios (DerSimonian-Laird)",
        "PM": "efeitos aleatórios (Paule-Mandel)",
        "FE": "efeito fixo",
    },
    "en": {
        "REML": "random effects (REML)",
        "DL": "random effects (DerSimonian-Laird)",
        "PM": "random effects (Paule-Mandel)",
        "FE": "fixed effect",
    },
}
CERTAINTY = {
    "pt-BR": {"very_low": "muito baixa", "low": "baixa", "moderate": "moderada", "high": "alta"},
    "en": {"very_low": "very low", "low": "low", "moderate": "moderate", "high": "high"},
}
T: dict[str, dict[str, str]] = {
    "pt-BR": {
        "objective": "Objetivo",
        "methods": "Métodos",
        "results": "Resultados",
        "conclusion": "Conclusão",
        "question": "{question}",
        "no_question": "[descreva o objetivo da revisão]",
        "search": "Buscamos em {databases} até {date}.",
        "no_search": "[descreva as bases consultadas e a data da última busca]",
        "selection": "Dois revisores triaram os registros de forma independente; conflitos foram resolvidos por consenso.",
        "rob": "O risco de viés foi avaliado com [instrumento].",
        "synthesis": "Os dados foram combinados em meta-análise com modelo de {model}{knha}.",
        "knha": " e ajuste de Hartung-Knapp",
        "flow": "Foram identificados {identified} registros; {duplicates} duplicatas foram removidas, {screened} registros foram triados e {assessed} textos completos foram avaliados. {included} estudos foram incluídos{meta}.",
        "flow_meta": ", {meta} deles na meta-análise",
        "effect": "No desfecho {outcome} ({timepoint}), considerando {k} estudos, o efeito combinado foi {measure} {pooled_effect} (IC 95% {ci_lower} a {ci_upper}; I² = {i2}).",
        "certainty": " A certeza da evidência foi {certainty} (GRADE).",
        "no_effect": "[descreva o resultado principal]",
        "conclusion_note": "[conclusão do grupo]",
        "methods_title": "Métodos",
        "results_title": "Resultados",
        "docx_title": "Rascunho de Métodos e Resultados",
        "docx_note": "Rascunho gerado pelo RevisaMeta com os números do sistema. Edite e confira antes de usar. Trechos entre colchetes precisam ser completados pelo grupo.",
        "extraction": "Os dados foram extraídos por dois revisores de forma independente, com consenso em caso de divergência.",
        "file": "rascunho-metodos-resultados",
    },
    "en": {
        "objective": "Objective",
        "methods": "Methods",
        "results": "Results",
        "conclusion": "Conclusion",
        "question": "{question}",
        "no_question": "[describe the objective of the review]",
        "search": "We searched {databases} up to {date}.",
        "no_search": "[describe the databases searched and the date of the last search]",
        "selection": "Two reviewers screened records independently; conflicts were resolved by consensus.",
        "rob": "Risk of bias was assessed with [tool].",
        "synthesis": "Data were pooled in a {model} meta-analysis{knha}.",
        "knha": " with the Hartung-Knapp adjustment",
        "flow": "We identified {identified} records; {duplicates} duplicates were removed, {screened} records were screened and {assessed} full texts were assessed. {included} studies were included{meta}.",
        "flow_meta": ", {meta} of them in the meta-analysis",
        "effect": "For {outcome} ({timepoint}), across {k} studies, the pooled effect was {measure} {pooled_effect} (95% CI {ci_lower} to {ci_upper}; I² = {i2}).",
        "certainty": " The certainty of the evidence was {certainty} (GRADE).",
        "no_effect": "[describe the main result]",
        "conclusion_note": "[the group's conclusion]",
        "methods_title": "Methods",
        "results_title": "Results",
        "docx_title": "Draft of Methods and Results",
        "docx_note": "Draft created by RevisaMeta with the system's numbers. Edit and check before use. Bracketed passages must be completed by the group.",
        "extraction": "Data were extracted by two reviewers independently, with consensus when they disagreed.",
        "file": "draft-methods-results",
    },
}


class DraftIn(BaseModel):
    lang: Lang = "pt-BR"
    analysis: RunIn | None = None


class Sections(BaseModel):
    objective: str
    methods: str
    results: str
    conclusion: str


class AbstractOut(BaseModel):
    text: str
    word_limit: int | None
    char_limit: int | None
    version: int | None


class AbstractIn(BaseModel):
    text: str = Field(max_length=20000)
    word_limit: int | None = Field(default=None, ge=1, le=10000)
    char_limit: int | None = Field(default=None, ge=1, le=100000)
    version: int | None = None


def _date(value: date, lang: str) -> str:
    return value.strftime("%d/%m/%Y" if lang == "pt-BR" else "%Y-%m-%d")


async def _sentences(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: DraftIn
) -> dict[str, str]:
    t = T[data.lang]
    out: dict[str, str] = {}
    out["objective"] = (ctx.project.question or "").strip() or t["no_question"]
    rows = await session.execute(
        select(Search.database, func.max(Search.search_date))
        .where(Search.project_id == ctx.project.id, Search.status == "done")
        .group_by(Search.database)
        .order_by(Search.database)
    )
    searches = rows.all()
    if searches:
        last = max(d for _, d in searches)
        out["search"] = t["search"].format(
            databases=", ".join(db for db, _ in searches), date=_date(last, data.lang)
        )
    else:
        out["search"] = t["no_search"]
    plan = current_plan(ctx)
    out["synthesis"] = t["synthesis"].format(
        model=MODEL[data.lang][plan.model.method],
        knha=t["knha"] if plan.model.method != "FE" and plan.model.test == "knha" else "",
    )
    flow = (await prisma_counts(session, ctx)).values
    meta = flow.get("studies_meta_analysis") or 0
    out["flow"] = t["flow"].format(
        identified=flow.get("identified_total", 0),
        duplicates=flow.get("duplicates_removed", 0),
        screened=flow.get("records_screened", 0),
        assessed=flow.get("reports_assessed", 0),
        included=flow.get("studies_included", 0),
        meta=t["flow_meta"].format(meta=meta) if meta else "",
    )
    out["effect"] = t["no_effect"]
    if data.analysis is not None:
        main = await run(session, ctx, stats, data.analysis)
        facts = facts_of(main.result, main.assembly.measure, data.lang)
        out["effect"] = t["effect"].format(
            outcome=main.assembly.outcome_name,
            timepoint=main.assembly.timepoint,
            measure=main.assembly.measure,
            **{k: facts.get(k, "—") for k in ("k", "pooled_effect", "ci_lower", "ci_upper", "i2")},
        )
        grade = (
            await session.scalars(
                select(GradeAssessment).where(
                    GradeAssessment.project_id == ctx.project.id,
                    GradeAssessment.outcome_id == data.analysis.outcome_id,
                    GradeAssessment.timepoint == data.analysis.timepoint,
                )
            )
        ).first()
        if grade is not None:
            out["effect"] += t["certainty"].format(
                certainty=CERTAINTY[data.lang][grade.final_certainty]
            )
    return out


async def abstract_draft(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: DraftIn
) -> Sections:
    s = await _sentences(session, ctx, stats, data)
    t = T[data.lang]
    return Sections(
        objective=s["objective"],
        methods=" ".join([s["search"], t["selection"], t["rob"], s["synthesis"]]),
        results=" ".join([s["flow"], s["effect"]]),
        conclusion=t["conclusion_note"],
    )


def sections_text(sections: Sections, lang: Lang) -> str:
    t = T[lang]
    return "\n\n".join(
        f"{t[key]}: {getattr(sections, key)}"
        for key in ("objective", "methods", "results", "conclusion")
    )


async def methods_results_docx(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: DraftIn
) -> tuple[bytes, str]:
    s = await _sentences(session, ctx, stats, data)
    t = T[data.lang]
    doc = Document()
    doc.add_heading(t["docx_title"], level=1)
    doc.add_paragraph(t["docx_note"])
    doc.add_heading(t["methods_title"], level=2)
    for text in (s["search"], t["selection"], t["extraction"], t["rob"], s["synthesis"]):
        doc.add_paragraph(text)
    doc.add_heading(t["results_title"], level=2)
    for text in (s["flow"], s["effect"]):
        doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return buffer.getvalue(), f"{_slug(ctx.project.title)}_{t['file']}_{day}.docx"


async def get_abstract(session: AsyncSession, ctx: ProjectContext) -> AbstractOut:
    row = (
        await session.scalars(
            select(AbstractDraft).where(AbstractDraft.project_id == ctx.project.id)
        )
    ).first()
    if row is None:
        return AbstractOut(text="", word_limit=None, char_limit=None, version=None)
    return AbstractOut(
        text=row.text, word_limit=row.word_limit, char_limit=row.char_limit, version=row.version
    )


async def save_abstract(
    session: AsyncSession, ctx: ProjectContext, data: AbstractIn
) -> AbstractOut:
    if not (EDITORS & ctx.roles):
        raise ForbiddenError()
    row = (
        await session.scalars(
            select(AbstractDraft).where(AbstractDraft.project_id == ctx.project.id)
        )
    ).first()
    if row is None:
        if data.version is not None:
            raise ConflictError()
        row = AbstractDraft(project_id=ctx.project.id, created_by=ctx.user.id)
        session.add(row)
    elif data.version != row.version:
        raise ConflictError()
    row.text, row.word_limit, row.char_limit = data.text, data.word_limit, data.char_limit
    await session.commit()
    await session.refresh(row)
    return await get_abstract(session, ctx)
