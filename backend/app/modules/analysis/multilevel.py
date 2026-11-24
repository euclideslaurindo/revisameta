"""Multilevel model for several results of the same study (docs/modulos.md 7.7, P2;
stage 8 step 2).

In the MVP each analysis uses one time point per study, so a study is never counted
twice. When the group wants to use every time point of an outcome together, the same
assembly (same rules, conversions and checks) runs for each time point; the effects are
then sent to R with the study as cluster (metafor::rma.mv, random = ~ 1 | study/effect),
which accounts for effects of the same study being correlated.
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.assembly import AssemblyIn, DataSet, Measure, assemble
from app.modules.projects.access import ProjectContext


class MultilevelIn(BaseModel):
    outcome_id: uuid.UUID
    timepoints: list[str] = Field(min_length=2, max_length=10)
    measure: Measure | None = None
    data_set: DataSet | None = None
    method: Literal["REML", "ML"] = "REML"
    test: Literal["z", "knha"] = "z"


class MultilevelOut(BaseModel):
    measure: str
    timepoints: list[str]
    k: int
    studies: int
    left_out: dict[str, list[str]]  # time point -> studies that did not enter
    result: dict[str, Any]  # pooled effect, variance components, Q (from R)
    warnings: list[str]


async def multilevel(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: MultilevelIn
) -> MultilevelOut:
    labels: list[str] = []
    clusters: list[str] = []
    yi: list[float] = []
    vi: list[float] = []
    left_out: dict[str, list[str]] = {}
    warnings: list[str] = []
    measure = data.measure
    for timepoint in dict.fromkeys(data.timepoints):
        assembly = await assemble(
            session,
            ctx,
            stats,
            AssemblyIn(
                outcome_id=data.outcome_id,
                timepoint=timepoint,
                measure=measure,
                data_set=data.data_set,
            ),
        )
        measure = assembly.measure  # every time point uses the same measure as the first
        warnings += assembly.warnings
        left_out[timepoint] = [s.label for s in assembly.studies if not s.included]
        for s in assembly.studies:
            if s.included and s.yi is not None and s.vi is not None:
                labels.append(f"{s.label} ({timepoint})")
                clusters.append(str(s.study_id))
                yi.append(s.yi)
                vi.append(s.vi)
    if len(set(clusters)) < 2:
        raise AppError("analysis.multilevel_too_few", status_code=409)
    response = await stats.multilevel(
        {
            "measure": measure,
            "method": data.method,
            "test": data.test,
            "data": {"label": labels, "study": clusters, "yi": yi, "vi": vi},
        }
    )
    if not response.ok:
        raise AppError("analysis.multilevel_too_few", status_code=409)
    return MultilevelOut(
        measure=str(measure),
        timepoints=list(dict.fromkeys(data.timepoints)),
        k=response.result["k"],
        studies=response.result["studies"],
        left_out=left_out,
        result=response.result,
        warnings=list(dict.fromkeys([*warnings, *response.warnings])),
    )
