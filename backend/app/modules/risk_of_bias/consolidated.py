"""Consolidated risk-of-bias table and plots (docs/modulos.md 7.6, stage 2 step 4).

- One table per instrument: studies x domains (or x questions, for checklists that
  have no domain judgements: JBI, Newcastle-Ottawa, generic), plus the overall
  judgement. Per-result instruments, and checklists with questions per outcome, are
  shown for one outcome and time point at a time.
- Only submitted consensus assessments (or imported ones) enter the table. Studies
  still being assessed are listed apart with the reason, never left out in silence.
- Plots are drawn by the R service (robvis, or ggplot2 with the same look; ADR-013),
  in the language chosen for the outputs, independent of the interface (ADR-008).
"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.integrations.stats_client import StatsClient
from app.modules.exports.extraction import _slug as slug
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias import assessments as asm
from app.modules.risk_of_bias.catalog import Template
from app.modules.risk_of_bias.models import RobAssessment, RobStudyTool, RobTool
from app.modules.risk_of_bias.rules import group_levels
from app.modules.studies.models import Study

FINAL_KINDS = ("consensus", "imported")

# ---- Labels of the outputs (pt-BR and en) --------------------------------------------

OUTPUT_LANGS = ("pt-BR", "en")

LEVEL_LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "low": "Baixo",
        "low_except_confounding": "Baixo (exceto pelo confundimento não controlado)",
        "some_concerns": "Algumas preocupações",
        "moderate": "Moderado",
        "high": "Alto",
        "serious": "Grave",
        "critical": "Crítico",
        "very_high": "Muito alto",
        "no_information": "Sem informação",
        "good": "Boa",
        "fair": "Razoável",
        "poor": "Ruim",
        "Y": "Sim",
        "PY": "Provavelmente sim",
        "PN": "Provavelmente não",
        "N": "Não",
        "NI": "Sem informação",
        "NA": "Não se aplica",
        "U": "Incerto",
        "SY": "Sim, forte",
        "WY": "Sim, fraco",
        "SN": "Não, forte",
        "WN": "Não, fraco",
    },
    "en": {
        "low": "Low",
        "low_except_confounding": "Low (except for concerns about uncontrolled confounding)",
        "some_concerns": "Some concerns",
        "moderate": "Moderate",
        "high": "High",
        "serious": "Serious",
        "critical": "Critical",
        "very_high": "Very high",
        "no_information": "No information",
        "good": "Good",
        "fair": "Fair",
        "poor": "Poor",
        "Y": "Yes",
        "PY": "Probably yes",
        "PN": "Probably no",
        "N": "No",
        "NI": "No information",
        "NA": "Not applicable",
        "U": "Unclear",
        "SY": "Yes, strong",
        "WY": "Yes, weak",
        "SN": "No, strong",
        "WN": "No, weak",
    },
}

PLOT_TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "overall": "Geral",
        "x_title": "Domínios de risco de viés",
        "x_title_questions": "Perguntas do checklist",
        "y_title": "Estudo",
        "judgement_title": "Julgamento",
        "not_applicable": "Não se aplica",
        "no_information": "Sem informação",
        "question": "Pergunta",
        "stars": "{n} de {max} estrela(s)",
    },
    "en": {
        "overall": "Overall",
        "x_title": "Risk of bias domains",
        "x_title_questions": "Checklist questions",
        "y_title": "Study",
        "judgement_title": "Judgement",
        "not_applicable": "Not applicable",
        "no_information": "No information",
        "question": "Question",
        "stars": "{n} of {max} star(s)",
    },
}


def level_label(key: str, lang: str) -> str:
    if key.startswith("stars_"):
        _, n, _, top = key.split("_")
        return PLOT_TEXTS[lang]["stars"].format(n=n, max=top)
    return LEVEL_LABELS[lang].get(key, key)


def _localized(value: dict[str, str] | None, lang: str) -> str:
    if not value:
        return ""
    return value.get(lang) or value.get("pt-BR") or next(iter(value.values()), "")


# ---- Schemas -------------------------------------------------------------------------


class ColumnOut(BaseModel):
    key: str
    short: str
    name: dict[str, str]
    kind: str  # domain | question


class RowOut(BaseModel):
    study_id: uuid.UUID
    label: str
    assessment_id: uuid.UUID
    kind: str  # consensus | imported
    values: dict[str, str | None]
    overall: str | None


class PendingOut(BaseModel):
    study_id: uuid.UUID
    label: str
    reason: str  # no_assessment | in_progress | consensus_pending


class TableOut(BaseModel):
    tool_id: uuid.UUID
    outcome_id: uuid.UUID | None
    timepoint: str | None
    needs_target: bool
    columns: list[ColumnOut]
    levels: list[str]  # every level that may appear, best first
    rows: list[RowOut]
    pending: list[PendingOut]


class PlotIn(BaseModel):
    tool_id: uuid.UUID
    outcome_id: uuid.UUID | None = None
    timepoint: str | None = Field(default=None, max_length=60)
    kind: Literal["traffic_light", "summary"]
    format: Literal["svg", "png"]
    lang: Literal["pt-BR", "en"] = "pt-BR"
    # Studies without a submitted consensus are left out only when the user says so.
    acknowledge_missing: bool = False


# ---- Table ---------------------------------------------------------------------------


def _uses_questions(template: Template) -> bool:
    return template.judgement.kind == "group_rule"


def needs_target(template: Template) -> bool:
    return template.scope == "result" or (
        _uses_questions(template)
        and any(q.level != "study" for d in template.domains for q in d.questions)
    )


def _stars_max(template: Template, answers: str) -> int | None:
    values = template.answer_sets[answers]
    return max(int(v) for v in values) if all(v.isdigit() for v in values) else None


def _columns(template: Template) -> list[ColumnOut]:
    if not _uses_questions(template):
        return [
            ColumnOut(
                key=d.key, short=f"D{i}", name=d.name.model_dump(by_alias=True), kind="domain"
            )
            for i, d in enumerate(template.domains, start=1)
        ]
    columns = []
    n = 0
    for d in template.domains:
        for q in d.questions:
            n += 1
            label = q.label or q.key
            columns.append(
                ColumnOut(
                    key=f"{d.key}.{q.key}",
                    short=f"Q{n}",
                    name={
                        lang: f"{_localized(d.name.model_dump(by_alias=True), lang)}: "
                        f"{PLOT_TEXTS[lang]['question'].lower()} {label}"
                        for lang in OUTPUT_LANGS
                    },
                    kind="question",
                )
            )
    return columns


def _levels(template: Template, tool: RobTool) -> list[str]:
    if not _uses_questions(template):
        return list(template.judgement.levels)
    answers: list[str] = []
    for d in template.domains:
        for q in d.questions:
            top = _stars_max(template, q.answers)
            values = (
                [f"stars_{n}_of_{top}" for n in range(top, -1, -1)]
                if top is not None
                else template.answer_sets[q.answers]
            )
            answers += [v for v in values if v not in answers]
    return answers + [lv for lv in group_levels(tool.overall_rule) if lv not in answers]


async def _tool(session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID) -> RobTool:
    tool = (
        await session.scalars(
            select(RobTool).where(RobTool.id == tool_id, RobTool.project_id == ctx.project.id)
        )
    ).first()
    if tool is None:
        raise NotFoundError()
    return tool


async def table(
    session: AsyncSession,
    ctx: ProjectContext,
    tool_id: uuid.UUID,
    outcome_id: uuid.UUID | None,
    timepoint: str | None,
) -> TableOut:
    tool = await _tool(session, ctx, tool_id)
    template = Template.model_validate(tool.structure)
    target_needed = needs_target(template)
    if target_needed:
        if outcome_id is None or not timepoint:
            raise AppError("rob.result_required", status_code=422)
        outcome = (
            await session.scalars(
                select(Outcome).where(
                    Outcome.id == outcome_id, Outcome.project_id == ctx.project.id
                )
            )
        ).first()
        if outcome is None or timepoint not in outcome.timepoints:
            raise AppError("rob.unknown_result", status_code=422)
    else:
        outcome_id, timepoint = None, None
    target = (outcome_id, timepoint) if template.scope == "result" else (None, None)

    studies = list(
        await session.execute(
            select(Study)
            .join(RobStudyTool, RobStudyTool.study_id == Study.id)
            .where(RobStudyTool.tool_id == tool.id, Study.project_id == ctx.project.id)
            .order_by(Study.label)
        )
    )
    assessments = list(
        await session.scalars(
            select(RobAssessment).where(
                RobAssessment.project_id == ctx.project.id, RobAssessment.tool_id == tool.id
            )
        )
    )
    columns = _columns(template)
    question_index = {f"{d.key}.{q.key}": q for d in template.domains for q in d.questions}
    targets = await asm._targets(session, ctx, template)
    rows: list[RowOut] = []
    pending: list[PendingOut] = []
    for (study,) in studies:
        mine = [
            a
            for a in assessments
            if a.study_id == study.id and (a.outcome_id, a.timepoint) == target
        ]
        final = next((a for a in mine if a.kind in FINAL_KINDS and a.status != "draft"), None)
        if final is None:
            individuals = [a for a in mine if a.kind == "individual"]
            submitted = [a for a in individuals if a.status != "draft"]
            reason = (
                "no_assessment"
                if not individuals
                else "in_progress"
                if len(submitted) < asm.reviewers_needed(ctx)
                else "consensus_pending"
            )
            pending.append(PendingOut(study_id=study.id, label=study.label, reason=reason))
            continue
        answers, judgements = await asm._rows(session, final)
        domains, overall, _ = asm.compute(template, tool, final, answers, judgements, targets)
        values: dict[str, str | None] = {}
        if _uses_questions(template):
            asked = {f"{d.domain_key}.{q}" for d in domains for q in d.asked}
            for column in columns:
                q = question_index[column.key]
                wanted: tuple[uuid.UUID | None, str | None] = (
                    (None, None)
                    if q.level == "study"
                    else (outcome_id, None)
                    if q.level == "outcome"
                    else (outcome_id, timepoint)
                )
                answer = next(
                    (
                        x.answer
                        for x in answers
                        if x.question_key == column.key and (x.outcome_id, x.timepoint) == wanted
                    ),
                    None,
                )
                if answer is not None and column.key not in asked:
                    answer = "NA"
                top = _stars_max(template, q.answers)
                if answer is not None and top is not None:
                    answer = f"stars_{answer}_of_{top}"
                values[column.key] = answer
        else:
            values = {d.domain_key: d.final for d in domains}
        rows.append(
            RowOut(
                study_id=study.id,
                label=study.label,
                assessment_id=final.id,
                kind=final.kind,
                values=values,
                overall=overall.final,
            )
        )
    return TableOut(
        tool_id=tool.id,
        outcome_id=outcome_id,
        timepoint=timepoint,
        needs_target=target_needed,
        columns=columns,
        levels=_levels(template, tool),
        rows=rows,
        pending=pending,
    )


# ---- Plots ---------------------------------------------------------------------------


async def plot(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: PlotIn
) -> tuple[bytes, str, list[str]]:
    """The figure (bytes and media type) and the studies left out of it."""
    t = await table(session, ctx, data.tool_id, data.outcome_id, data.timepoint)
    if not t.rows:
        raise AppError("rob.nothing_to_plot", status_code=409)
    if t.pending and not data.acknowledge_missing:
        raise AppError("rob.plot_missing_studies", status_code=409, count=len(t.pending))
    lang = data.lang
    texts = dict(PLOT_TEXTS[lang])
    if t.columns and t.columns[0].kind == "question":
        texts["x_title"] = texts["x_title_questions"]
    used = {v for r in t.rows for v in [*r.values.values(), r.overall] if v}
    spec: dict[str, Any] = {
        "kind": data.kind,
        "format": data.format,
        "overall": True,
        "texts": texts,
        "columns": [
            {"key": c.key, "short": c.short, "name": _localized(c.name, lang)} for c in t.columns
        ],
        "levels": [{"key": lv, "label": level_label(lv, lang)} for lv in t.levels if lv in used],
        "studies": [{"label": r.label, "values": r.values, "overall": r.overall} for r in t.rows],
    }
    response = await stats.rob_plot(spec)
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    content = base64.b64decode(response.result["file_base64"])
    return content, response.result["content_type"], [p.label for p in t.pending]


def plot_file_name(ctx: ProjectContext, data: PlotIn) -> str:
    kind = {
        ("pt-BR", "traffic_light"): "risco-de-vies-semaforo",
        ("pt-BR", "summary"): "risco-de-vies-resumo",
        ("en", "traffic_light"): "risk-of-bias-traffic-light",
        ("en", "summary"): "risk-of-bias-summary",
    }[(data.lang, data.kind)]
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{slug(ctx.project.title)}_{kind}_{day}.{data.format}"
