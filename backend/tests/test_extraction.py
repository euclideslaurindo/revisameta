"""Extraction: form versions, blind individual extractions, arms, scales and numbers."""

from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _join(
    client: AsyncClient, admin: LoggedUser, guest: LoggedUser, pid: str, roles: list[str]
) -> None:
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": roles}, headers=admin.headers
    )
    await client.post(
        f"/api/v1/invitations/{r.json()['link'].split('token=')[1]}/accept", headers=guest.headers
    )


async def _project(client: AsyncClient, admin: LoggedUser) -> dict[str, str]:
    pid = (
        await client.post("/api/v1/projects", json={"title": "P"}, headers=admin.headers)
    ).json()["id"]
    base = f"/api/v1/projects/{pid}"
    outcome = (
        await client.post(
            f"{base}/outcomes",
            json={"name": "QI", "type": "continuous", "timepoints": ["5 anos"]},
            headers=admin.headers,
        )
    ).json()
    group = (
        await client.post(
            f"{base}/comparison-groups", json={"label": "< 5 anos"}, headers=admin.headers
        )
    ).json()
    study = (
        await client.post(
            f"{base}/studies",
            json={"label": "Exemplo 2020", "design": "other", "reference": {"title": "Fictício"}},
            headers=admin.headers,
        )
    ).json()
    return {
        "pid": pid,
        "base": base,
        "outcome": outcome["id"],
        "group": group["id"],
        "study": study["id"],
    }


async def _start(client: AsyncClient, user: LoggedUser, p: dict[str, str]) -> dict[str, Any]:
    r = await client.post(f"{p['base']}/studies/{p['study']}/extractions", headers=user.headers)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_default_form_and_new_versions(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    form = (await client.get(f"{p['base']}/extraction-form", headers=ana.headers)).json()
    assert form["form_version"] == 1
    keys = [f["key"] for f in form["schema"]["fields"]]
    assert {"country", "n_total", "cutoff_used", "funding"} <= set(keys)

    extraction = await _start(client, ana, p)
    fields = form["schema"]["fields"] + [
        {
            "key": "anesthesia",
            "type": "select",
            "label": "Tipo de anestesia",
            "options": ["geral", "local"],
        }
    ]
    r = await client.put(
        f"{p['base']}/extraction-form",
        json={"version": form["version"], "schema": {"fields": fields}},
        headers=ana.headers,
    )
    assert r.json()["form_version"] == 2
    listed = (
        await client.get(f"{p['base']}/studies/{p['study']}/extractions", headers=ana.headers)
    ).json()
    assert listed[0]["id"] == extraction["id"]
    assert listed[0]["outdated_form"] is True

    bad = {"fields": [{"key": "Bad Key", "type": "text", "label": "x"}]}
    r = await client.put(
        f"{p['base']}/extraction-form", json={"version": 1, "schema": bad}, headers=ana.headers
    )
    assert r.status_code == 422


async def test_characteristics_autosave_validates_types(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    ex = await _start(client, ana, p)
    url = f"{p['base']}/extractions/{ex['id']}"
    r = await client.patch(
        url,
        json={"version": ex["version"], "characteristics": {"country": "Brasil", "n_total": "120"}},
        headers=ana.headers,
    )
    assert r.status_code == 200
    r = await client.patch(
        url,
        json={"version": r.json()["version"], "characteristics": {"centers": "dois"}},
        headers=ana.headers,
    )
    assert r.json()["code"] == "extraction.invalid_field"
    r = await client.patch(
        url, json={"version": 2, "characteristics": {"unknown": "x"}}, headers=ana.headers
    )
    assert r.json()["code"] == "extraction.invalid_field"
    detail = (await client.get(url, headers=ana.headers)).json()
    assert detail["characteristics"] == {"country": "Brasil", "n_total": 120.0}


async def test_individual_extractions_are_blind_and_limited(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    bia = await make_user()
    caio = await make_user()
    dani = await make_user()
    p = await _project(client, ana)
    for user in (bia, caio, dani):
        await _join(client, ana, user, p["pid"], ["extractor"])

    mine = await _start(client, bia, p)
    assert (await _start(client, bia, p))["id"] == mine["id"]  # idempotent
    other = await _start(client, caio, p)
    r = await client.post(f"{p['base']}/studies/{p['study']}/extractions", headers=dani.headers)
    assert r.json()["code"] == "extraction.enough_extractors"

    seen_by_bia = (
        await client.get(f"{p['base']}/studies/{p['study']}/extractions", headers=bia.headers)
    ).json()
    assert [e["id"] for e in seen_by_bia] == [mine["id"]]
    assert (
        await client.get(f"{p['base']}/extractions/{other['id']}", headers=bia.headers)
    ).status_code == 404
    seen_by_admin = (
        await client.get(f"{p['base']}/studies/{p['study']}/extractions", headers=ana.headers)
    ).json()
    assert {e["id"] for e in seen_by_admin} == {mine["id"], other["id"]}
    r = await client.post(
        f"{p['base']}/extractions/{other['id']}/arms", json={"label": "x"}, headers=ana.headers
    )
    assert r.status_code == 403  # admins see, but do not type into someone else's extraction


async def test_single_extraction_when_double_extraction_is_off(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    bia = await make_user()
    p = await _project(client, ana)
    project = (await client.get(p["base"], headers=ana.headers)).json()
    await client.patch(
        p["base"],
        json={"version": project["version"], "double_extraction": False},
        headers=ana.headers,
    )
    await _join(client, ana, bia, p["pid"], ["extractor"])
    await _start(client, ana, p)
    r = await client.post(f"{p['base']}/studies/{p['study']}/extractions", headers=bia.headers)
    assert r.json()["code"] == "extraction.enough_extractors"


async def test_readers_and_reviewers_cannot_start(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    reviewer = await make_user()
    p = await _project(client, ana)
    await _join(client, ana, reviewer, p["pid"], ["reviewer"])
    r = await client.post(f"{p['base']}/studies/{p['study']}/extractions", headers=reviewer.headers)
    assert r.status_code == 403


async def test_arms_scales_and_numbers_bump_the_data_version(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    ex = await _start(client, ana, p)
    base = f"{p['base']}/extractions/{ex['id']}"

    early = (
        await client.post(
            f"{base}/arms",
            json={"label": "Operados < 5 anos", "n": 30, "mapped_group_id": p["group"]},
            headers=ana.headers,
        )
    ).json()
    late = (
        await client.post(
            f"{base}/arms", json={"label": "Operados >= 5 anos", "n": 28}, headers=ana.headers
        )
    ).json()
    r = await client.post(
        f"{base}/arms", json={"label": "x", "mapped_group_id": p["study"]}, headers=ana.headers
    )
    assert r.json()["code"] == "extraction.unknown_group"

    r = await client.put(
        f"{base}/measures/{p['outcome']}",
        json={
            "scale_name": "Escala fictícia",
            "scale_min": 40,
            "scale_max": 160,
            "higher_is_better": True,
        },
        headers=ana.headers,
    )
    assert r.json()["scale_name"] == "Escala fictícia"
    r = await client.put(
        f"{base}/measures/{p['outcome']}",
        json={"scale_min": 10, "scale_max": 5},
        headers=ana.headers,
    )
    assert r.json()["code"] == "extraction.invalid_scale_range"

    row = {
        "arm_id": early["id"],
        "outcome_id": p["outcome"],
        "timepoint": "5 anos",
        "n": 30,
        "mean": "92.5",
        "dispersion_type": "sd",
        "sd": "11.2",
        "dispersion_source": "Rodapé da Tabela 2",
        "source_location": "p. 4, Tabela 2",
    }
    created = (await client.post(f"{base}/outcome-data", json=row, headers=ana.headers)).json()
    assert created["mean"] == "92.5"
    assert created["dispersion_type"] == "sd"

    r = await client.put(
        f"{p['base']}/outcome-data/{created['id']}",
        json={
            "version": 1,
            "values": {"n": 30, "mean": "93.0", "dispersion_type": "se", "se": "2.04"},
        },
        headers=ana.headers,
    )
    assert r.json()["se"] == "2.04"
    assert r.json()["sd"] is None

    detail = (await client.get(base, headers=ana.headers)).json()
    assert detail["data_version"] == 6  # 2 arms + 1 scale + create + update = 5 changes
    assert [a["label"] for a in detail["arms"]] == ["Operados < 5 anos", "Operados >= 5 anos"]
    assert len(detail["outcome_data"]) == 1

    r = await client.delete(f"{p['base']}/arms/{early['id']}", headers=ana.headers)
    assert r.json()["code"] == "extraction.arm_in_use"
    assert (
        await client.delete(f"{p['base']}/arms/{late['id']}", headers=ana.headers)
    ).status_code == 204
    assert (
        await client.delete(f"{p['base']}/outcome-data/{created['id']}", headers=ana.headers)
    ).status_code == 204


@pytest.mark.parametrize(
    ("values", "code_part"),
    [
        ({"sd": "5"}, "dispersion_type_required"),
        ({"dispersion_type": "sd", "se": "1"}, "dispersion_mismatch"),
        ({"dispersion_type": "ci95", "sd": "1"}, "dispersion_mismatch"),
    ],
)
async def test_dispersion_needs_a_matching_type(
    client: AsyncClient, make_user: MakeUser, values: dict[str, str], code_part: str
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    ex = await _start(client, ana, p)
    base = f"{p['base']}/extractions/{ex['id']}"
    arm = (await client.post(f"{base}/arms", json={"label": "A"}, headers=ana.headers)).json()
    r = await client.post(
        f"{base}/outcome-data",
        json={"arm_id": arm["id"], "outcome_id": p["outcome"], "timepoint": "5 anos", **values},
        headers=ana.headers,
    )
    assert r.status_code == 422
    assert code_part in r.text


async def test_rows_must_use_protocol_items_and_own_arms(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    ex = await _start(client, ana, p)
    base = f"{p['base']}/extractions/{ex['id']}"
    arm = (await client.post(f"{base}/arms", json={"label": "A"}, headers=ana.headers)).json()
    row = {"arm_id": arm["id"], "outcome_id": p["outcome"], "timepoint": "10 anos"}
    r = await client.post(f"{base}/outcome-data", json=row, headers=ana.headers)
    assert r.json()["code"] == "extraction.unknown_timepoint"
    r = await client.post(
        f"{base}/outcome-data",
        json={**row, "timepoint": "5 anos", "arm_id": p["group"]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "extraction.unknown_arm"
    r = await client.post(
        f"{base}/outcome-data",
        json={**row, "timepoint": "5 anos", "annotation_id": p["group"]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "extraction.unknown_annotation"


async def test_submitted_extraction_is_frozen(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    ex = await _start(client, ana, p)
    r = await client.post(f"{p['base']}/extractions/{ex['id']}/submit", headers=ana.headers)
    assert r.json()["status"] == "submitted"
    r = await client.post(
        f"{p['base']}/extractions/{ex['id']}/arms", json={"label": "A"}, headers=ana.headers
    )
    assert r.json()["code"] == "extraction.not_editable"
