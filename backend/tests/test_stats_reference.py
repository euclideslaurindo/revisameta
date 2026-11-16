"""Statistical reference tests through the Python client (docs/validacao.md 11.1, item 3).

The same metafor fixtures used by the R tests are sent by the backend's own client to
the real R service, and the answers must match within the fixture tolerance. Nothing
here is computed in Python: it only compares what R returned with what metafor wrote
in the fixture.

The fixtures live in stats-r/fixtures (mounted at /stats-fixtures in the test
container) and the R service must be running (STATS_R_URL); CI starts it too.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from app.integrations.stats_client import StatsClient


def _fixture() -> dict[str, Any]:
    for base in (
        Path(__file__).resolve().parents[2] / "stats-r" / "fixtures",
        Path("/stats-fixtures"),
    ):
        path = base / "meta-analysis.json"
        if path.exists():
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
    raise FileNotFoundError("stats-r/fixtures/meta-analysis.json not found")


FIXTURE = _fixture()
CASES = FIXTURE["cases"]


def _close(actual: float, expected: float, name: str, what: str) -> None:
    tol = FIXTURE["tolerance"]
    assert math.isclose(actual, expected, rel_tol=0, abs_tol=tol), (
        f"{name}: {what} {actual} != {expected}"
    )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
async def test_meta_analysis_matches_metafor(case: dict[str, Any]) -> None:
    response = await StatsClient().meta_analysis(case["request"])
    assert response.ok, response.errors
    result, expected = response.result, case["expected"]
    pooled, het = result["pooled"], result["heterogeneity"]
    assert result["k"] == expected["k"]
    for key in ("estimate", "se", "ci_lb", "ci_ub", "statistic", "p_value", "pi_lb", "pi_ub"):
        _close(pooled[key], expected[key], case["name"], key)
    for key in ("tau2", "i2", "h2", "q", "q_p"):
        _close(het[key], expected[key], case["name"], key)
    for study, yi, vi, weight in zip(
        result["studies"], expected["yi"], expected["vi"], expected["weights"], strict=True
    ):
        _close(study["yi"], yi, case["name"], "yi")
        _close(study["vi"], vi, case["name"], "vi")
        _close(study["weight"], weight, case["name"], "weight")
    # Every answer says which versions computed it (8.1).
    assert response.meta.packages["metafor"] == FIXTURE["metafor_version"]


async def test_effect_sizes_match_metafor() -> None:
    case = next(c for c in CASES if c["name"] == "dat.bcg_OR_REML_knha")
    response = await StatsClient().effect_sizes({"measure": "OR", "data": case["request"]["data"]})
    assert response.ok
    for study, yi in zip(response.result["studies"], case["expected"]["yi"], strict=True):
        _close(study["yi"], yi, case["name"], "yi")
