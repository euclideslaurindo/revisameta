"""Synthetic cases for the extraction safeguards (docs/validacao.md 11.2, blocks A and C)."""

from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _setup(
    client: AsyncClient, admin: LoggedUser, higher_is_better: bool = True
) -> dict[str, Any]:
    pid = (
        await client.post("/api/v1/projects", json={"title": "P"}, headers=admin.headers)
    ).json()["id"]
    base = f"/api/v1/projects/{pid}"
    outcome = (
        await client.post(
            f"{base}/outcomes",
            json={
                "name": "Escore",
                "type": "continuous",
                "timepoints": ["5 anos"],
                "higher_is_better": higher_is_better,
            },
            headers=admin.headers,
        )
    ).json()
    early = (
        await client.post(
            f"{base}/comparison-groups",
            json={"label": "< 5 anos", "position": 1},
            headers=admin.headers,
        )
    ).json()
    late = (
        await client.post(
            f"{base}/comparison-groups",
            json={"label": ">= 5 anos", "position": 2},
            headers=admin.headers,
        )
    ).json()
    study = (
        await client.post(
            f"{base}/studies",
            json={"label": "Ficticio 2020", "design": "other", "reference": {"title": "Exemplo"}},
            headers=admin.headers,
        )
    ).json()
    ex = (
        await client.post(f"{base}/studies/{study['id']}/extractions", headers=admin.headers)
    ).json()
    eb = f"{base}/extractions/{ex['id']}"
    arm_a = (
        await client.post(
            f"{eb}/arms",
            json={"label": "Precoce", "n": 30, "mapped_group_id": early["id"]},
            headers=admin.headers,
        )
    ).json()
    arm_b = (
        await client.post(
            f"{eb}/arms",
            json={"label": "Tardio", "n": 28, "mapped_group_id": late["id"]},
            headers=admin.headers,
        )
    ).json()
    return {
        "pid": pid,
        "base": base,
        "eb": eb,
        "ex": ex,
        "study": study["id"],
        "outcome": outcome["id"],
        "arm_a": arm_a["id"],
        "arm_b": arm_b["id"],
    }


def _row(s: dict[str, Any], arm: str, **values: Any) -> dict[str, Any]:
    return {"arm_id": s[arm], "outcome_id": s["outcome"], "timepoint": "5 anos", **values}


async def _alerts(client: AsyncClient, user: LoggedUser, s: dict[str, Any]) -> list[dict[str, Any]]:
    return list((await client.get(f"{s['eb']}/alerts", headers=user.headers)).json())


def _codes(alerts: list[dict[str, Any]], status: str = "open") -> set[str]:
    return {a["code"] for a in alerts if a["status"] == status}


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"n": 0}, "extraction.impossible.n_not_positive"),
        ({"dispersion_type": "sd", "sd": "0"}, "extraction.impossible.sd_not_positive"),
        ({"dispersion_type": "se", "se": "-1"}, "extraction.impossible.se_not_positive"),
        ({"events": 12, "total": 10}, "extraction.impossible.events_gt_total"),
        ({"events": -1, "total": 10}, "extraction.impossible.negative_events"),
        (
            {"dispersion_type": "ci95", "ci_low": "90", "ci_high": "80"},
            "extraction.impossible.ci_inverted",
        ),
        ({"dispersion_type": "iqr", "q1": "10", "q3": "5"}, "extraction.impossible.iqr_inverted"),
        (
            {"dispersion_type": "range", "min": "10", "max": "5"},
            "extraction.impossible.range_inverted",
        ),
        (
            {"dispersion_type": "iqr", "median": "20", "q1": "5", "q3": "10"},
            "extraction.impossible.median_outside",
        ),
        ({"p_value": "1.5"}, "extraction.impossible.p_out_of_range"),
        ({"p_value": "0"}, "extraction.impossible.p_out_of_range"),
        (
            {"effect_reported": {"measure": "OR", "estimate": "-0.4"}},
            "extraction.impossible.ratio_not_positive",
        ),
        (
            {
                "effect_reported": {
                    "measure": "HR",
                    "estimate": "1.2",
                    "ci_low": "0",
                    "ci_high": "2",
                }
            },
            "extraction.impossible.ratio_not_positive",
        ),
        (
            {"effect_reported": {"measure": "MD", "estimate": "3", "ci_low": "5", "ci_high": "1"}},
            "extraction.impossible.ci_inverted",
        ),
        (
            {"effect_reported": {"measure": "SMD", "estimate": "0.3", "se": "0"}},
            "extraction.impossible.se_not_positive",
        ),
    ],
)
async def test_impossible_values_are_blocked(
    client: AsyncClient, make_user: MakeUser, values: dict[str, Any], code: str
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    r = await client.post(
        f"{s['eb']}/outcome-data", json=_row(s, "arm_a", **values), headers=ana.headers
    )
    assert r.status_code == 422
    assert r.json()["code"] == code


async def test_impossible_value_is_also_blocked_on_update_and_for_arms(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    row = (
        await client.post(
            f"{s['eb']}/outcome-data", json=_row(s, "arm_a", n=30), headers=ana.headers
        )
    ).json()
    r = await client.put(
        f"{s['base']}/outcome-data/{row['id']}",
        json={"version": row["version"], "values": {"dispersion_type": "sd", "sd": "-2"}},
        headers=ana.headers,
    )
    assert r.json()["code"] == "extraction.impossible.sd_not_positive"
    r = await client.post(f"{s['eb']}/arms", json={"label": "x", "n": 0}, headers=ana.headers)
    assert r.json()["code"] == "extraction.impossible.n_not_positive"


async def test_arms_adding_up_to_more_than_the_study_block_submission_until_justified(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    await client.patch(
        s["eb"],
        json={"version": detail["version"], "characteristics": {"n_total": 50}},
        headers=ana.headers,
    )

    alerts = await _alerts(client, ana, s)
    block = next(a for a in alerts if a["code"] == "extraction.alert.arms_exceed_total")
    assert block["severity"] == "block"
    assert block["params"] == {"sum": 58, "total": "50"}

    r = await client.post(f"{s['eb']}/submit", headers=ana.headers)
    assert r.json()["code"] == "extraction.open_blocking_alerts"

    r = await client.post(
        f"{s['base']}/alerts/{block['id']}/justify",
        json={"justification": "ok"},
        headers=ana.headers,
    )
    assert r.status_code == 422  # justification too short
    r = await client.post(
        f"{s['base']}/alerts/{block['id']}/justify",
        json={"justification": "O artigo inclui participantes de outro centro na Tabela 1."},
        headers=ana.headers,
    )
    assert r.json()["status"] == "justified"
    audit = (
        await session.scalars(
            select(AuditLog).where(
                AuditLog.entity == "check_alerts", AuditLog.field == "justification"
            )
        )
    ).all()
    assert len(audit) == 1
    assert (await client.post(f"{s['eb']}/submit", headers=ana.headers)).json()[
        "status"
    ] == "submitted"


async def test_warnings_appear_and_resolve_when_values_are_fixed(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await client.put(
        f"{s['eb']}/measures/{s['outcome']}",
        json={"scale_min": 40, "scale_max": 160},
        headers=ana.headers,
    )
    row = (
        await client.post(
            f"{s['eb']}/outcome-data",
            json=_row(
                s, "arm_a", n=30, mean="170", dispersion_type="ci95", ci_low="100", ci_high="120"
            ),
            headers=ana.headers,
        )
    ).json()
    codes = _codes(await _alerts(client, ana, s))
    assert {
        "extraction.alert.mean_outside_scale",
        "extraction.alert.ci_excludes_mean",
        "extraction.alert.dispersion_unconfirmed",
        "extraction.alert.no_source",
    } <= codes
    # With a single group typed there is no sentence yet, so nothing to confirm.
    assert "extraction.alert.direction_unconfirmed" not in codes

    r = await client.put(
        f"{s['base']}/outcome-data/{row['id']}",
        json={
            "version": row["version"],
            "values": {
                "n": 30,
                "mean": "110",
                "dispersion_type": "sd",
                "sd": "70",
                "dispersion_source": "Rodape da Tabela 2",
                "source_location": "p. 4",
            },
        },
        headers=ana.headers,
    )
    assert r.status_code == 200
    alerts = await _alerts(client, ana, s)
    codes = _codes(alerts)
    assert "extraction.alert.sd_too_large" in codes  # 70 > (160 - 40) / 2
    assert (
        not {
            "extraction.alert.mean_outside_scale",
            "extraction.alert.ci_excludes_mean",
            "extraction.alert.no_source",
            "extraction.alert.dispersion_unconfirmed",
        }
        & codes
    )


async def test_justification_reopens_when_the_value_changes(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await client.put(
        f"{s['eb']}/measures/{s['outcome']}",
        json={"scale_min": 40, "scale_max": 160},
        headers=ana.headers,
    )
    row = (
        await client.post(
            f"{s['eb']}/outcome-data",
            json=_row(s, "arm_a", mean="170", source_location="p. 2"),
            headers=ana.headers,
        )
    ).json()
    alert = next(
        a
        for a in await _alerts(client, ana, s)
        if a["code"] == "extraction.alert.mean_outside_scale"
    )
    await client.post(
        f"{s['base']}/alerts/{alert['id']}/justify",
        json={"justification": "Escala estendida no artigo."},
        headers=ana.headers,
    )
    assert "extraction.alert.mean_outside_scale" in _codes(
        await _alerts(client, ana, s), "justified"
    )

    await client.put(
        f"{s['base']}/outcome-data/{row['id']}",
        json={"version": row["version"], "values": {"mean": "180", "source_location": "p. 2"}},
        headers=ana.headers,
    )
    assert "extraction.alert.mean_outside_scale" in _codes(await _alerts(client, ana, s))


async def _two_means(
    client: AsyncClient, user: LoggedUser, s: dict[str, Any], a: str, b: str
) -> None:
    for arm, mean in (("arm_a", a), ("arm_b", b)):
        await client.post(
            f"{s['eb']}/outcome-data",
            json=_row(s, arm, n=30, mean=mean, source_location="p. 3"),
            headers=user.headers,
        )


async def test_direction_sentence_data_follows_the_scale_direction(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await _two_means(client, ana, s, "92", "85")
    [summary] = (await client.get(f"{s['eb']}/direction", headers=ana.headers)).json()
    assert summary["first"]["group_label"] == "< 5 anos"
    assert summary["first"]["mean"] == "92"
    assert summary["favors"] == "first"
    assert summary["confirmed"] is False

    # Same numbers on a scale where higher is worse: the other group is favoured.
    await client.put(
        f"{s['eb']}/measures/{s['outcome']}", json={"higher_is_better": False}, headers=ana.headers
    )
    [summary] = (await client.get(f"{s['eb']}/direction", headers=ana.headers)).json()
    assert summary["favors"] == "second"


async def test_confirming_the_direction_clears_the_alert_until_numbers_change(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await _two_means(client, ana, s, "92", "85")
    alerts = await _alerts(client, ana, s)
    [direction_alert] = [a for a in alerts if a["code"] == "extraction.alert.direction_unconfirmed"]
    r = await client.post(
        f"{s['base']}/alerts/{direction_alert['id']}/justify",
        json={"justification": "confere com o artigo"},
        headers=ana.headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "extraction.alert_confirm_direction"
    r = await client.post(
        f"{s['eb']}/direction/confirm",
        json={"outcome_id": s["outcome"], "timepoint": "5 anos"},
        headers=ana.headers,
    )
    assert r.json()[0]["confirmed"] is True
    assert "extraction.alert.direction_unconfirmed" not in _codes(await _alerts(client, ana, s))

    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    row = next(r for r in detail["outcome_data"] if r["arm_id"] == s["arm_a"])
    await client.put(
        f"{s['base']}/outcome-data/{row['id']}",
        json={
            "version": row["version"],
            "values": {"n": 30, "mean": "80", "source_location": "p. 3"},
        },
        headers=ana.headers,
    )
    assert "extraction.alert.direction_unconfirmed" in _codes(await _alerts(client, ana, s))
    [summary] = (await client.get(f"{s['eb']}/direction", headers=ana.headers)).json()
    assert summary["favors"] == "second"


async def _confirm(client: AsyncClient, user: LoggedUser, s: dict[str, Any]) -> bool:
    r = await client.post(
        f"{s['eb']}/direction/confirm",
        json={"outcome_id": s["outcome"], "timepoint": "5 anos"},
        headers=user.headers,
    )
    return bool(r.json()[0]["confirmed"])


async def _confirmed(client: AsyncClient, user: LoggedUser, s: dict[str, Any]) -> bool:
    [summary] = (await client.get(f"{s['eb']}/direction", headers=user.headers)).json()
    return bool(summary["confirmed"])


async def test_saving_other_fields_keeps_the_confirmed_direction(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await _two_means(client, ana, s, "92", "85")
    assert await _confirm(client, ana, s)

    # Autosave sends the whole row; changing the source (and trying to send the flag
    # from the client) must neither clear nor set the confirmation.
    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    row = next(r for r in detail["outcome_data"] if r["arm_id"] == s["arm_a"])
    r = await client.put(
        f"{s['base']}/outcome-data/{row['id']}",
        json={
            "version": row["version"],
            "values": {
                "n": 30,
                "mean": "92.0",
                "source_location": "Tabela 2",
                "direction_confirmed": False,
            },
        },
        headers=ana.headers,
    )
    assert r.status_code == 200
    assert r.json()["direction_confirmed"] is True
    assert await _confirmed(client, ana, s)
    assert "extraction.alert.direction_unconfirmed" not in _codes(await _alerts(client, ana, s))


async def test_scale_direction_and_group_link_clear_the_confirmation(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await _two_means(client, ana, s, "92", "85")
    assert await _confirm(client, ana, s)
    await client.put(
        f"{s['eb']}/measures/{s['outcome']}", json={"higher_is_better": True}, headers=ana.headers
    )
    await client.put(
        f"{s['eb']}/measures/{s['outcome']}", json={"higher_is_better": False}, headers=ana.headers
    )
    assert not await _confirmed(client, ana, s)

    assert await _confirm(client, ana, s)
    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    arm_b = next(a for a in detail["arms"] if a["id"] == s["arm_b"])
    await client.patch(
        f"{s['base']}/arms/{arm_b['id']}",
        json={"version": arm_b["version"], "mapped_group_id": None},
        headers=ana.headers,
    )
    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    flags = {r["arm_id"]: r["direction_confirmed"] for r in detail["outcome_data"]}
    assert flags == {s["arm_a"]: True, s["arm_b"]: False}


async def test_no_sentence_without_two_mapped_groups(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    await client.post(
        f"{s['eb']}/arms", json={"label": "Terceiro grupo", "n": 10}, headers=ana.headers
    )
    await _two_means(client, ana, s, "92", "85")
    assert len((await client.get(f"{s['eb']}/direction", headers=ana.headers)).json()) == 1
    detail = (await client.get(s["eb"], headers=ana.headers)).json()
    arm_b = next(a for a in detail["arms"] if a["id"] == s["arm_b"])
    await client.patch(
        f"{s['base']}/arms/{arm_b['id']}",
        json={"version": arm_b["version"], "mapped_group_id": None},
        headers=ana.headers,
    )
    assert (await client.get(f"{s['eb']}/direction", headers=ana.headers)).json() == []


async def test_pending_checks_respect_blinding(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    bia = await make_user()
    caio = await make_user()
    s = await _setup(client, ana)
    for user in (bia, caio):
        r = await client.post(
            f"{s['base']}/invitations", json={"roles": ["extractor"]}, headers=ana.headers
        )
        await client.post(
            f"/api/v1/invitations/{r.json()['link'].split('token=')[1]}/accept",
            headers=user.headers,
        )
    # ana (admin) already has one extraction; bia takes the second slot.
    bia_ex = (
        await client.post(f"{s['base']}/studies/{s['study']}/extractions", headers=bia.headers)
    ).json()
    bia_arm = (
        await client.post(
            f"{s['base']}/extractions/{bia_ex['id']}/arms", json={"label": "A"}, headers=bia.headers
        )
    ).json()
    await client.post(
        f"{s['base']}/extractions/{bia_ex['id']}/outcome-data",
        json={"arm_id": bia_arm["id"], "outcome_id": s["outcome"], "timepoint": "5 anos", "n": 5},
        headers=bia.headers,
    )
    await client.post(f"{s['eb']}/outcome-data", json=_row(s, "arm_a", n=30), headers=ana.headers)

    mine = (await client.get(f"{s['base']}/pending-checks", headers=bia.headers)).json()
    assert {p["extraction_id"] for p in mine} == {bia_ex["id"]}
    assert mine[0]["study_label"] == "Ficticio 2020"
    everyone = (await client.get(f"{s['base']}/pending-checks", headers=ana.headers)).json()
    assert {p["extraction_id"] for p in everyone} == {bia_ex["id"], s["ex"]["id"]}
    assert (await client.get(f"{s['base']}/pending-checks", headers=caio.headers)).json() == []

    alert = mine[0]
    r = await client.post(
        f"{s['base']}/alerts/{alert['id']}/justify",
        json={"justification": "conferido no artigo"},
        headers=caio.headers,
    )
    assert r.status_code == 404  # blind: caio cannot even see bia's extraction
    r = await client.post(
        f"{s['base']}/alerts/{alert['id']}/justify",
        json={"justification": "conferido no artigo"},
        headers=ana.headers,
    )
    assert r.status_code == 403  # admins see, but only the extractor confirms


async def test_reported_effect_outside_its_ci_is_an_alert_and_kept_on_save(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    s = await _setup(client, ana)
    effect = {"measure": "OR", "estimate": "2.5", "ci_low": "1.1", "ci_high": "2.0"}
    row = (
        await client.post(
            f"{s['eb']}/outcome-data",
            json=_row(
                s,
                "arm_a",
                effect_reported=effect,
                adjusted=True,
                adjusted_for="idade",
                p_value="0.03",
                source_location="Tabela 3",
            ),
            headers=ana.headers,
        )
    ).json()
    assert row["effect_reported"]["estimate"] == "2.5"
    assert row["adjusted"] is True and row["p_value"] == "0.03"
    alerts = await _alerts(client, ana, s)
    [alert] = [a for a in alerts if a["code"] == "extraction.alert.effect_outside_ci"]
    assert alert["params"] == {"estimate": "2.5", "low": "1.1", "high": "2"}
    # A row with only a reported effect still needs its origin in the article.
    assert "extraction.alert.no_source" not in _codes(alerts)
