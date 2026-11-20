"""Publication bias: Egger's test and the funnel plot (docs/modulos.md 7.7; stage 4 step 3).

Same studies, model and test as the main analysis. With fewer than 10 studies the
answer always says so (few_studies), and the screen shows it as a strong warning:
neither the funnel nor Egger can be read as a conclusion then (CLAUDE.md 0.2).
"""

import base64
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.run import RunIn, run
from app.modules.exports.extraction import _slug
from app.modules.projects.access import ProjectContext

FEW = "fewer_than_ten_studies"


class EggerOut(BaseModel):
    measure: str
    k: int
    few_studies: bool
    result: dict[str, Any]  # statistic, df, p_value, limit estimate (from R)
    warnings: list[str]


class FunnelIn(RunIn):
    format: Literal["svg", "png"] = "svg"
    lang: Literal["pt-BR", "en"] = "pt-BR"


TEXTS = {
    "pt-BR": {"se": "Erro-padrão", "file": "funnel-plot"},
    "en": {"se": "Standard error", "file": "funnel-plot"},
}


async def _spec(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: RunIn
) -> tuple[dict[str, Any], str, str]:
    main = await run(session, ctx, stats, data)
    spec = {**(main.assembly.request or {}), "method": main.method, "test": main.test}
    return spec, main.assembly.measure, main.assembly.outcome_name


async def egger(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: RunIn
) -> EggerOut:
    spec, measure, _ = await _spec(session, ctx, stats, data)
    response = await stats.egger(spec)
    if not response.ok:
        raise AppError("analysis.egger_needs_three", status_code=409)
    warnings = list(dict.fromkeys(response.warnings))
    return EggerOut(
        measure=measure,
        k=response.result["k"],
        few_studies=FEW in warnings,
        result=response.result,
        warnings=warnings,
    )


async def funnel_plot(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: FunnelIn
) -> tuple[bytes, str, str]:
    spec, measure, outcome = await _spec(session, ctx, stats, data)
    t = TEXTS[data.lang]
    response = await stats.funnel_plot(
        {
            **spec,
            "format": data.format,
            "decimal_mark": "," if data.lang == "pt-BR" else ".",
            "texts": {"effect": measure, "se": t["se"]},
        }
    )
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    content = base64.b64decode(response.result["file_base64"])
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    name = f"{_slug(ctx.project.title)}_{t['file']}_{_slug(outcome)}_{day}.{data.format}"
    return content, response.result["content_type"], name
