"""Meta-regression (docs/modulos.md 7.7, P2; stage 8 step 1).

Moderators come from the consensus extraction form (e.g. mean age at surgery, follow-up
length, type of surgery) or the cut-off used by the study. A number in the field enters
as a numeric moderator; anything else as a category. Studies without a value for some
moderator are left out and listed. The R service fits the model and gives the strong
warning below 10 studies per moderator (approved rule; Cochrane Handbook); with fewer
than 3 studies it does not run.
"""

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.run import RunIn, run
from app.modules.analysis.subgroups import _text
from app.modules.extraction.models import Extraction
from app.modules.projects.access import ProjectContext
from app.modules.protocol.analysis_plan import parse_cutoff

NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")
CUTOFF = "cutoff_used"


class MetaRegressionIn(RunIn):
    moderators: list[str] = Field(min_length=1, max_length=5)  # form field keys or "cutoff_used"


class MetaRegressionOut(BaseModel):
    measure: str
    moderators: list[str]
    kinds: dict[str, str]  # numeric | categorical
    values: dict[str, dict[str, Any]]  # moderator -> study label -> value
    left_out: list[str]
    result: dict[str, Any]  # coefficients, test of moderators, residual heterogeneity (R)
    warnings: list[str]


def _value(raw: Any, key: str) -> float | str | None:
    if key == CUTOFF:
        return parse_cutoff(raw)
    if isinstance(raw, bool):
        return _text(str(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    text = _text(raw)
    if text is not None and NUMBER.match(text):
        return float(text.replace(",", "."))
    return text


async def meta_regression(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: MetaRegressionIn
) -> MetaRegressionOut:
    main = await run(session, ctx, stats, data)
    included = [s for s in main.assembly.studies if s.included]
    consensus = {
        e.study_id: e
        for e in await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id,
                Extraction.kind == "consensus",
                Extraction.study_id.in_([s.study_id for s in included]),
            )
        )
    }
    request = main.assembly.request or {}
    payload = request.get("data", {})
    labels: list[str] = payload.get("label", [])
    by_label = {s.label: s for s in included}
    values: dict[str, dict[str, Any]] = {}
    columns: dict[str, list[Any]] = {}
    kinds: dict[str, str] = {}
    for key in dict.fromkeys(data.moderators):
        column: list[Any] = []
        for label in labels:
            study = by_label.get(label)
            e = consensus.get(study.study_id) if study else None
            column.append(_value((e.characteristics or {}).get(key) if e else None, key))
        # A moderator is numeric only when every known value is a number.
        known = [v for v in column if v is not None]
        numeric = bool(known) and all(isinstance(v, float) for v in known)
        if not numeric:
            column = [
                None if v is None else (f"{v:g}" if isinstance(v, float) else v) for v in column
            ]
        kinds[key] = "numeric" if numeric else "categorical"
        columns[key] = column
        values[key] = {label: v for label, v in zip(labels, column, strict=True) if v is not None}
    response = await stats.meta_regression(
        {
            **request,
            "method": main.method,
            "test": main.test,
            "data": {**payload, "mods": columns},
        }
    )
    if not response.ok:
        raise AppError("analysis.meta_regression_too_few", status_code=409)
    return MetaRegressionOut(
        measure=main.assembly.measure,
        moderators=list(columns),
        kinds=kinds,
        values=values,
        left_out=list(response.result.get("left_out", [])),
        result=response.result,
        warnings=list(dict.fromkeys(response.warnings)),
    )
