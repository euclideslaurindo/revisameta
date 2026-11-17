"""Pre-defined analysis plan (stage 3 step 3)."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.protocol.analysis_plan import AnalysisPlan, cutoff_status, parse_cutoff
from tests.test_consensus import MakeUser, _join, _project


async def _plan(client: AsyncClient, user: Any, p: dict[str, Any]) -> Any:
    return await client.get(f"{p['base']}/analysis-plan", headers=user.headers)


async def test_plan_defaults_validation_and_permissions(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])

    plan = (await _plan(client, bia, p)).json()
    assert plan["defined"] is False
    # Stage 3 decision: REML with Hartung-Knapp by default; adjusted effects apart.
    assert plan["model"] == {"method": "REML", "test": "knha"}
    assert plan["adjusted"] == "separate"

    body = {
        "version": plan["version"],
        "comparison": {"group1_id": p["groups"][0], "group2_id": p["groups"][1]},
        "cutoff": {
            "value": 5,
            "unit": "years",
            "rule": "tolerant",
            "tolerance_min": 4,
            "tolerance_max": 6,
        },
        "outcomes": [{"outcome_id": p["outcome"], "measure": "SMD", "timepoint": "5 anos"}],
        "sensitivity": ["leave_one_out", "exclude_high_risk_of_bias", "leave_one_out"],
        "subgroups": ["  tipo de cirurgia ", ""],
    }
    url = f"{p['base']}/analysis-plan"
    assert (await client.put(url, json=body, headers=bia.headers)).status_code == 403
    r = await client.put(url, json=body, headers=ana.headers)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["defined"] is True and saved["version"] > plan["version"]
    assert saved["sensitivity"] == ["leave_one_out", "exclude_high_risk_of_bias"]
    assert saved["subgroups"] == ["tipo de cirurgia"]
    assert (await _plan(client, bia, p)).json()["cutoff"]["tolerance_max"] == 6

    # The old version is refused: two people never overwrite each other.
    r = await client.put(url, json=body, headers=ana.headers)
    assert r.status_code == 409

    fresh = saved["version"]
    bad = [
        (
            {**body, "outcomes": [{"outcome_id": p["outcome"], "measure": "OR"}]},
            "plan.measure_mismatch",
        ),
        (
            {**body, "outcomes": [{"outcome_id": p["outcome"], "timepoint": "99 anos"}]},
            "plan.unknown_timepoint",
        ),
        (
            {**body, "comparison": {"group1_id": p["groups"][0], "group2_id": p["outcome"]}},
            "plan.unknown_group",
        ),
    ]
    for payload, code in bad:
        r = await client.put(url, json={**payload, "version": fresh}, headers=ana.headers)
        assert r.json()["code"] == code, r.text
    r = await client.put(
        url,
        json={**body, "version": fresh, "cutoff": {"value": 5, "rule": "tolerant"}},
        headers=ana.headers,
    )
    assert r.status_code == 422  # a tolerant rule needs its range
    r = await client.put(
        url,
        json={**body, "version": fresh, "model": {"method": "FE", "test": "knha"}},
        headers=ana.headers,
    )
    assert r.json()["model"] == {"method": "FE", "test": "z"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5.0),
        ("5", 5.0),
        ("5,5", 5.5),
        (" 4.0 ", 4.0),
        ("< 5 anos", None),
        ("cinco", None),
        (None, None),
        (True, None),
    ],
)
def test_parse_cutoff_never_interprets_text(value: Any, expected: float | None) -> None:
    assert parse_cutoff(value) == expected


def test_cutoff_status_follows_the_rule() -> None:
    strict = AnalysisPlan.model_validate({"cutoff": {"value": 5}})
    tolerant = AnalysisPlan.model_validate(
        {"cutoff": {"value": 5, "rule": "tolerant", "tolerance_min": 4, "tolerance_max": 6}}
    )
    assert cutoff_status("5", strict) == "match"
    assert cutoff_status(6, strict) == "incompatible"
    assert cutoff_status(6, tolerant) == "tolerated"
    assert cutoff_status(7, tolerant) == "incompatible"
    assert cutoff_status("antes dos 5 anos", tolerant) == "not_numeric"
    assert cutoff_status(None, tolerant) == "missing"
    assert cutoff_status(5, AnalysisPlan()) == "no_rule"
