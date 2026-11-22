"""PRISMA 2020 flow diagram (docs/modulos.md 7.9; stage 5 step 6).

Counts come from the system (searches, deduplication, the two screening stages,
studies and saved analyses). A person can type a count instead (with a justification),
for groups that imported only the final list. The figure is drawn by the R service in
the output language; counting is plain arithmetic, no statistics.

PRISMA 2020 boxes and where each count comes from:
- identified per database: references imported from each search (before deduplication);
- duplicates removed: references a person confirmed as duplicates;
- records screened: title/abstract references (no duplicates);
- records excluded: title/abstract final "exclude" (agreed or resolved);
- reports sought: title/abstract final "include";
- reports not retrieved: full text excluded with the reason "full text unavailable";
- reports assessed: full text final decisions, minus those not retrieved;
- reports excluded: full text final "exclude", per reason;
- studies included / reports of included studies: studies and reports of the project;
- studies in a meta-analysis: studies in at least one saved analysis.
"""

import base64
import io
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from docx import Document
from docx.shared import Inches
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.models import Analysis
from app.modules.exports.extraction import _slug
from app.modules.prisma.models import PrismaAdjustment
from app.modules.projects.access import ProjectContext
from app.modules.references.models import Search
from app.modules.screening.models import ExclusionReason
from app.modules.screening.service import _ids, _state
from app.modules.studies.models import Reference, Report, Study

ADJUSTABLE = (
    "identified_total",
    "duplicates_removed",
    "records_screened",
    "records_excluded",
    "reports_sought",
    "reports_not_retrieved",
    "reports_assessed",
    "reports_excluded_total",
    "studies_included",
    "reports_included",
    "studies_meta_analysis",
)
Key = Literal[
    "identified_total",
    "duplicates_removed",
    "records_screened",
    "records_excluded",
    "reports_sought",
    "reports_not_retrieved",
    "reports_assessed",
    "reports_excluded_total",
    "studies_included",
    "reports_included",
    "studies_meta_analysis",
]
NOT_RETRIEVED = "full_text_unavailable"
Lang = Literal["pt-BR", "en"]


class DatabaseCount(BaseModel):
    database: str
    n: int


class ReasonCount(BaseModel):
    reason_id: uuid.UUID | None
    key: str | None
    label: str | None
    n: int


class Adjustment(BaseModel):
    value: int
    justification: str
    computed: int


class PrismaCounts(BaseModel):
    identified: list[DatabaseCount]
    reports_excluded: list[ReasonCount]
    values: dict[str, int]  # final value of each adjustable count
    computed: dict[str, int]  # what the system counted
    adjusted: dict[str, Adjustment]
    pending: dict[str, int]  # still waiting: title_abstract / full_text
    warnings: list[str]


class AdjustIn(BaseModel):
    value: int | None = Field(default=None, ge=0)  # None removes the adjustment
    justification: str | None = Field(default=None, max_length=1000)


class FlowIn(BaseModel):
    format: Literal["svg", "png"] = "svg"
    lang: Lang = "pt-BR"


async def _final(session: AsyncSession, ctx: ProjectContext, stage: Any) -> dict[uuid.UUID, Any]:
    state = await _state(session, ctx, stage)
    return {i: (state.status(i), state.reason(i)) for i in await _ids(session, ctx, stage)}


async def counts(session: AsyncSession, ctx: ProjectContext) -> PrismaCounts:
    pid = ctx.project.id
    identified = [
        DatabaseCount(database=db, n=n)
        for db, n in (
            await session.execute(
                select(Search.database, func.sum(Search.record_count))
                .where(Search.project_id == pid, Search.status == "done")
                .group_by(Search.database)
                .order_by(Search.database)
            )
        ).all()
    ]
    duplicates = await session.scalar(
        select(func.count())
        .select_from(Reference)
        .where(
            Reference.project_id == pid,
            Reference.search_id.is_not(None),
            Reference.duplicate_of.is_not(None),
        )
    )
    ta = await _final(session, ctx, "title_abstract")
    ft = await _final(session, ctx, "full_text")
    reasons = {
        r.id: r
        for r in await session.scalars(
            select(ExclusionReason)
            .where(ExclusionReason.project_id == pid)
            .execution_options(include_deleted=True)
        )
    }
    ta_status = Counter(s for s, _ in ta.values())
    ft_status = Counter(s for s, _ in ft.values())
    excluded_reasons: Counter[uuid.UUID | None] = Counter(
        r for s, r in ft.values() if s in ("exclude", "resolved_exclude")
    )
    not_retrieved_ids = {i for i, r in reasons.items() if r.key == NOT_RETRIEVED}
    not_retrieved = sum(n for r, n in excluded_reasons.items() if r in not_retrieved_ids)
    ft_final = sum(
        ft_status[s] for s in ("include", "exclude", "resolved_include", "resolved_exclude")
    )
    reports_excluded = [
        ReasonCount(
            reason_id=r,
            key=reasons[r].key if r in reasons else None,
            label=reasons[r].label if r in reasons else None,
            n=n,
        )
        for r, n in sorted(excluded_reasons.items(), key=lambda x: -x[1])
        if r not in not_retrieved_ids
    ]
    analysed: set[str] = set()
    for ids in await session.scalars(
        select(Analysis.included_study_ids).where(Analysis.project_id == pid)
    ):
        analysed.update(ids or [])
    computed = {
        "identified_total": sum(d.n for d in identified),
        "duplicates_removed": duplicates or 0,
        "records_screened": len(ta),
        "records_excluded": ta_status["exclude"] + ta_status["resolved_exclude"],
        "reports_sought": ta_status["include"] + ta_status["resolved_include"],
        "reports_not_retrieved": not_retrieved,
        "reports_assessed": ft_final - not_retrieved,
        "reports_excluded_total": sum(r.n for r in reports_excluded),
        "studies_included": await session.scalar(
            select(func.count()).select_from(Study).where(Study.project_id == pid)
        )
        or 0,
        "reports_included": await session.scalar(
            select(func.count()).select_from(Report).where(Report.project_id == pid)
        )
        or 0,
        "studies_meta_analysis": len(analysed),
    }
    adjusted: dict[str, Adjustment] = {}
    for a in await session.scalars(
        select(PrismaAdjustment).where(PrismaAdjustment.project_id == pid)
    ):
        adjusted[a.key] = Adjustment(
            value=a.value, justification=a.justification, computed=computed[a.key]
        )
    values = {k: (adjusted[k].value if k in adjusted else v) for k, v in computed.items()}
    pending = {
        "title_abstract": ta_status["pending"] + ta_status["conflict"],
        "full_text": ft_status["pending"] + ft_status["conflict"],
    }
    return PrismaCounts(
        identified=identified,
        reports_excluded=reports_excluded,
        values=values,
        computed=computed,
        adjusted=adjusted,
        pending=pending,
        warnings=_warnings(values, pending),
    )


def _warnings(v: dict[str, int], pending: dict[str, int]) -> list[str]:
    """Counts that do not add up, so nobody sends an inconsistent diagram unawares."""
    out = []
    if pending["title_abstract"]:
        out.append("title_abstract_pending")
    if pending["full_text"]:
        out.append("full_text_pending")
    if v["identified_total"] - v["duplicates_removed"] != v["records_screened"]:
        out.append("screened_does_not_add_up")
    if not pending["title_abstract"] and (
        v["records_screened"] - v["records_excluded"] != v["reports_sought"]
    ):
        out.append("sought_does_not_add_up")
    if not pending["full_text"] and (
        v["reports_sought"] - v["reports_not_retrieved"] != v["reports_assessed"]
    ):
        out.append("assessed_does_not_add_up")
    return out


async def adjust(
    session: AsyncSession, ctx: ProjectContext, key: Key, data: AdjustIn
) -> PrismaCounts:
    if not ctx.is_admin:
        raise ForbiddenError()
    current = (
        await session.scalars(
            select(PrismaAdjustment).where(
                PrismaAdjustment.project_id == ctx.project.id, PrismaAdjustment.key == key
            )
        )
    ).first()
    if data.value is None:
        if current is not None:
            current.deleted_at = datetime.now(UTC)
    else:
        justification = (data.justification or "").strip()
        if len(justification) < 3:
            raise AppError("prisma.justification_required", status_code=422)
        if current is None:
            session.add(
                PrismaAdjustment(
                    project_id=ctx.project.id,
                    key=key,
                    value=data.value,
                    justification=justification,
                    created_by=ctx.user.id,
                )
            )
        else:
            current.value = data.value
            current.justification = justification
    await session.commit()
    return await counts(session, ctx)


# ---- Texts of the boxes (output language) -----------------------------------------------

TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "title": "Fluxograma PRISMA 2020",
        "phase_identification": "Identificação",
        "phase_screening": "Triagem",
        "phase_included": "Incluídos",
        "identified": "Registros identificados:",
        "total": "Total",
        "removed": "Registros removidos antes da triagem:",
        "duplicates": "Duplicatas",
        "screened": "Registros triados",
        "screened_excluded": "Registros excluídos",
        "sought": "Relatos buscados para leitura",
        "not_retrieved": "Relatos não obtidos",
        "assessed": "Relatos avaliados quanto à elegibilidade",
        "assessed_excluded": "Relatos excluídos:",
        "included": "Estudos incluídos na revisão",
        "reports_included": "Relatos dos estudos incluídos",
        "meta": "Estudos incluídos em meta-análise",
        "adjusted": "*",
        "adjusted_note": "* contagem ajustada manualmente",
        "no_reason": "Sem motivo",
        "file": "prisma-fluxograma",
    },
    "en": {
        "title": "PRISMA 2020 flow diagram",
        "phase_identification": "Identification",
        "phase_screening": "Screening",
        "phase_included": "Included",
        "identified": "Records identified from:",
        "total": "Total",
        "removed": "Records removed before screening:",
        "duplicates": "Duplicate records",
        "screened": "Records screened",
        "screened_excluded": "Records excluded",
        "sought": "Reports sought for retrieval",
        "not_retrieved": "Reports not retrieved",
        "assessed": "Reports assessed for eligibility",
        "assessed_excluded": "Reports excluded:",
        "included": "Studies included in review",
        "reports_included": "Reports of included studies",
        "meta": "Studies included in meta-analysis",
        "adjusted": "*",
        "adjusted_note": "* count adjusted by hand",
        "no_reason": "No reason",
        "file": "prisma-flow-diagram",
    },
}
REASON_TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "wrong_population": "População errada",
        "wrong_design": "Desenho de estudo errado",
        "no_comparison_group": "Sem grupo de comparação",
        "no_outcome_data": "Sem dados do desfecho",
        "incompatible_cutoff": "Ponto de corte incompatível",
        "duplicate_cohort": "Mesma coorte de outro estudo",
        "full_text_unavailable": "Texto completo indisponível",
    },
    "en": {
        "wrong_population": "Wrong population",
        "wrong_design": "Wrong study design",
        "no_comparison_group": "No comparison group",
        "no_outcome_data": "No outcome data",
        "incompatible_cutoff": "Incompatible cut-off",
        "duplicate_cohort": "Same cohort as another study",
        "full_text_unavailable": "Full text unavailable",
    },
}


def boxes(c: PrismaCounts, lang: Lang) -> dict[str, str]:
    t = TEXTS[lang]
    v = c.values

    def n(key: str) -> str:
        mark = t["adjusted"] if key in c.adjusted else ""
        return f"(n = {v[key]}){mark}"

    identified = [t["identified"]] + [f"  {d.database} (n = {d.n})" for d in c.identified]
    if len(c.identified) != 1 or "identified_total" in c.adjusted:
        identified.append(f"  {t['total']} {n('identified_total')}")
    excluded = [t["assessed_excluded"]]
    for r in c.reports_excluded:
        name = r.label or (REASON_TEXTS[lang].get(r.key or "") if r.key else None) or t["no_reason"]
        excluded.append(f"  {name} (n = {r.n})")
    if "reports_excluded_total" in c.adjusted or len(c.reports_excluded) != 1:
        excluded.append(f"  {t['total']} {n('reports_excluded_total')}")
    included = [t["included"], n("studies_included"), t["reports_included"], n("reports_included")]
    if v["studies_meta_analysis"]:
        included += [t["meta"], n("studies_meta_analysis")]
    if c.adjusted:
        included += ["", t["adjusted_note"]]
    return {
        "identified": "\n".join(identified),
        "removed": f"{t['removed']}\n  {t['duplicates']} {n('duplicates_removed')}",
        "screened": f"{t['screened']}\n{n('records_screened')}",
        "screened_excluded": f"{t['screened_excluded']}\n{n('records_excluded')}",
        "sought": f"{t['sought']}\n{n('reports_sought')}",
        "not_retrieved": f"{t['not_retrieved']}\n{n('reports_not_retrieved')}",
        "assessed": f"{t['assessed']}\n{n('reports_assessed')}",
        "assessed_excluded": "\n".join(excluded),
        "included": "\n".join(included),
    }


async def flow(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: FlowIn
) -> tuple[bytes, str, str]:
    c = await counts(session, ctx)
    t = TEXTS[data.lang]
    response = await stats.prisma_flow(
        {
            "format": data.format,
            "title": t["title"],
            "phases": [t["phase_identification"], t["phase_screening"], t["phase_included"]],
            "boxes": boxes(c, data.lang),
        }
    )
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    content = base64.b64decode(response.result["file_base64"])
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    name = f"{_slug(ctx.project.title)}_{t['file']}_{day}.{data.format}"
    return content, response.result["content_type"], name


async def flow_docx(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, lang: Lang
) -> tuple[bytes, str]:
    """The figure (PNG, 300 dpi) and, below it, the counts with any adjustment explained."""
    png, _, name = await flow(session, ctx, stats, FlowIn(format="png", lang=lang))
    c = await counts(session, ctx)
    t = TEXTS[lang]
    doc = Document()
    doc.add_heading(t["title"], level=1)
    doc.add_picture(io.BytesIO(png), width=Inches(6.3))
    if c.adjusted:
        doc.add_paragraph(t["adjusted_note"])
        for key, a in c.adjusted.items():
            doc.add_paragraph(
                f"{key}: {a.value} ({a.computed}) — {a.justification}", style="List Bullet"
            )
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue(), name.rsplit(".", 1)[0] + ".docx"
