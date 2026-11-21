"""Running an analysis and drawing its forest plot (docs/modulos.md 7.7; stage 3 step 5).

The data come from the assembly (who enters and with which numbers); the model and
the plot are computed by the R service. Nothing is saved yet: the history of analyses
arrives in step 7. Settings that differ from the analysis plan are reported as
"not planned".
"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.assembly import AssemblyIn, AssemblyOut, StudyRow, assemble
from app.modules.exports.extraction import _slug
from app.modules.projects.access import ProjectContext
from app.modules.protocol.analysis_plan import current_plan
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.risk_of_bias.consolidated import PLOT_TEXTS, _localized, level_label
from app.modules.risk_of_bias.consolidated import table as rob_table

Method = Literal["REML", "DL", "PM", "FE"]
Test = Literal["knha", "z"]


class RunIn(AssemblyIn):
    method: Method | None = None  # None: from the plan
    test: Test | None = None


class RunOut(BaseModel):
    assembly: AssemblyOut
    method: Method
    test: Test
    not_planned: list[str]
    result: dict[str, Any]  # what R returned: pooled, heterogeneity, studies
    warnings: list[str]
    r_meta: dict[str, Any]  # R and package versions, parameters (8.1)
    group1_label: str | None
    group2_label: str | None
    favours_right: Literal["group1", "group2"]


class ForestIn(RunIn):
    format: Literal["svg", "png"] = "svg"
    lang: Literal["pt-BR", "en"] = "pt-BR"
    # The risk-of-bias traffic light beside each study (ADR-014), from this tool.
    rob_tool_id: uuid.UUID | None = None


TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "study": "Estudo",
        "effect": "{measure} [IC 95%]",
        "favours": "Favorece {group}",
        "group1": "grupo 1",
        "group2": "grupo 2",
        "REML": "Efeitos aleatórios (REML",
        "DL": "Efeitos aleatórios (DerSimonian-Laird",
        "PM": "Efeitos aleatórios (Paule-Mandel",
        "FE": "Efeito fixo (",
        "knha": ", Hartung-Knapp)",
        "z": ")",
        "note_converted": "dados convertidos (ex.: DP a partir do EP ou do IC)",
        "note_estimated": "média e DP estimados a partir da mediana",
        "note_derived": "efeito derivado da estatística t ou do valor p",
        "file": "forest-plot",
        "rob_title": "Risco de viés",
        "rob_missing": (
            "Célula vazia: estudo sem avaliação final de risco de viés com este instrumento."
        ),
    },
    "en": {
        "study": "Study",
        "effect": "{measure} [95% CI]",
        "favours": "Favours {group}",
        "group1": "group 1",
        "group2": "group 2",
        "REML": "Random effects (REML",
        "DL": "Random effects (DerSimonian-Laird",
        "PM": "Random effects (Paule-Mandel",
        "FE": "Fixed effect (",
        "knha": ", Hartung-Knapp)",
        "z": ")",
        "note_converted": "converted data (e.g. SD from the SE or the CI)",
        "note_estimated": "mean and SD estimated from the median",
        "note_derived": "effect derived from the t statistic or the p value",
        "file": "forest-plot",
        "rob_title": "Risk of bias",
        "rob_missing": "Empty cells: study without a final risk-of-bias assessment with this tool.",
    },
}


def _model_label(lang: str, method: str, test: str) -> str:
    t = TEXTS[lang]
    if method == "FE":
        return t["FE"].rstrip(" (")
    return t[method] + t[test]


async def _groups(session: AsyncSession, ctx: ProjectContext) -> tuple[str | None, str | None]:
    plan = current_plan(ctx)
    if plan.comparison is None:
        return None, None
    labels = {
        g.id: g.label
        for g in await session.scalars(
            select(ComparisonGroup).where(ComparisonGroup.project_id == ctx.project.id)
        )
    }
    return labels.get(plan.comparison.group1_id), labels.get(plan.comparison.group2_id)


async def _favours_right(
    session: AsyncSession, ctx: ProjectContext, data: RunIn
) -> Literal["group1", "group2"]:
    """Which group the right side of the plot favours.

    Continuous: after the per-study inversion done by R, higher always means better,
    so a positive effect favours group 1. Dichotomous: it depends on whether the event
    is desirable (the outcome's direction).
    """
    outcome = await session.get(Outcome, data.outcome_id)
    if outcome is None or outcome.type == "continuous" or outcome.higher_is_better:
        return "group1"
    return "group2"


async def run(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: RunIn
) -> RunOut:
    assembly = await assemble(session, ctx, stats, data)
    if assembly.blocks or assembly.request is None:
        raise AppError("analysis.blocked", status_code=409, blocks=", ".join(assembly.blocks))
    plan = current_plan(ctx)
    method: Method = data.method or plan.model.method
    test: Test = data.test or plan.model.test
    if method == "FE":
        test = "z"
    not_planned = list(assembly.not_planned)
    if method != plan.model.method or (method != "FE" and test != plan.model.test):
        not_planned.append("model")
    request = {**assembly.request, "method": method, "test": test}
    response = await stats.meta_analysis(request)
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    warnings = [*assembly.warnings, *response.warnings]
    influence = await stats.influence({**request, "params": plan.checks.model_dump()})
    if influence.ok:
        by_label = {s["label"]: s for s in influence.result.get("studies", [])}
        for study in assembly.studies:
            info = by_label.get(study.label)
            if not study.included or info is None:
                continue
            for flag, key in (("influential", "influential"), ("improbable_effect", "improbable")):
                if info.get(key) and flag not in study.flags:
                    study.flags.append(flag)
        if any(s.get("influential") for s in by_label.values()):
            warnings.append("influential_studies")
        if any(s.get("improbable") for s in by_label.values()):
            warnings.append("improbable_effects")
        warnings += influence.warnings
    group1, group2 = await _groups(session, ctx)
    return RunOut(
        assembly=assembly,
        method=method,
        test=test,
        not_planned=not_planned,
        result=response.result,
        warnings=list(dict.fromkeys(warnings)),
        r_meta=response.meta.model_dump(),
        group1_label=group1,
        group2_label=group2,
        favours_right=await _favours_right(session, ctx, data),
    )


def _marker(flags: list[str]) -> str:
    for flag in ("estimated", "derived", "converted"):
        if flag in flags:
            return flag
    return ""


async def _rob_columns(
    session: AsyncSession, ctx: ProjectContext, data: ForestIn, included: list[StudyRow]
) -> dict[str, Any]:
    """Traffic light columns from the consolidated risk-of-bias table of one tool."""
    tool_id = data.rob_tool_id or uuid.UUID(int=0)
    table = await rob_table(session, ctx, tool_id, data.outcome_id, data.timepoint)
    by_study = {r.study_id: r for r in table.rows}
    used = {v for r in table.rows for v in [*r.values.values(), r.overall] if v}
    studies = []
    for s in included:
        row = by_study.get(s.study_id)
        studies.append(
            {
                "values": [row.values.get(c.key) if row else None for c in table.columns],
                "overall": row.overall if row else None,
            }
        )
    return {
        "columns": [
            {"short": c.short, "name": _localized(c.name, data.lang)} for c in table.columns
        ],
        "levels": [
            {"key": lv, "label": level_label(lv, data.lang)} for lv in table.levels if lv in used
        ],
        "studies": studies,
    }


async def forest_plot(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: ForestIn
) -> tuple[bytes, str, str]:
    out = await run(session, ctx, stats, data)
    t = TEXTS[data.lang]
    included = [s for s in out.assembly.studies if s.included]
    names = {
        "group1": out.group1_label or t["group1"],
        "group2": out.group2_label or t["group2"],
    }
    right = out.favours_right
    left = "group2" if right == "group1" else "group1"
    spec = {
        **(out.assembly.request or {}),
        "method": out.method,
        "test": out.test,
        "format": data.format,
        "decimal_mark": "," if data.lang == "pt-BR" else ".",
        "markers": [_marker(s.flags) for s in included],
        "texts": {
            "study": t["study"],
            "effect": t["effect"].format(measure=out.assembly.measure),
            "favours_left": t["favours"].format(group=names[left]),
            "favours_right": t["favours"].format(group=names[right]),
            "model": _model_label(data.lang, out.method, out.test),
            "note_converted": t["note_converted"],
            "note_estimated": t["note_estimated"],
            "note_derived": t["note_derived"],
        },
    }
    if data.rob_tool_id is not None:
        spec["rob"] = await _rob_columns(session, ctx, data, included)
        spec["texts"].update(
            {
                "rob_title": t["rob_title"],
                "rob_missing": t["rob_missing"],
                "rob_overall": PLOT_TEXTS[data.lang]["overall"],
            }
        )
    response = await stats.forest_plot(spec)
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    content = base64.b64decode(response.result["file_base64"])
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    outcome = _slug(out.assembly.outcome_name)
    name = f"{_slug(ctx.project.title)}_{t['file']}_{outcome}_{day}.{data.format}"
    return content, response.result["content_type"], name
