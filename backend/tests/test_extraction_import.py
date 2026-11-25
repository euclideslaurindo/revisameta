"""Importing an extraction spreadsheet the group already has (7.2, P0).

The spreadsheet is FICTITIOUS (made-up studies and numbers), only to exercise the rules.
"""

import json
from typing import Any

from httpx import AsyncClient, Response

from tests.conftest import LoggedUser
from tests.test_extraction import MakeUser, _join, _project

HEADER = "estudo;grupo;n;desfecho;momento;media;dp;ep;pagina\n"
SHEET = (
    HEADER
    + "Ficticio A 2020;< 5 anos;20;QI;5 anos;92,5;10;;Tabela 2\n"
    + "Ficticio A 2020;>= 5 anos;25;QI;5 anos;85;11;;Tabela 2\n"
    + "Ficticio B 2021;Precoce;18;QI;5 anos;90;;2,1;p. 4\n"
    + "Ficticio B 2021;Tardio;22;QI;5 anos;88;-3;;p. 4\n"
    + "Desconhecido 1999;Precoce;10;QI;5 anos;1;1;;\n"
)


async def _setup(client: AsyncClient, admin: LoggedUser) -> dict[str, Any]:
    p: dict[str, Any] = await _project(client, admin)
    late = (
        await client.post(
            f"{p['base']}/comparison-groups", json={"label": ">= 5 anos"}, headers=admin.headers
        )
    ).json()
    p["late"] = late["id"]
    for label in ("Ficticio A 2020", "Ficticio B 2021"):
        r = await client.post(
            f"{p['base']}/studies",
            json={"label": label, "design": "other", "reference": {"title": label}},
            headers=admin.headers,
        )
        p[label] = r.json()["id"]
    return p


async def _send(
    client: AsyncClient,
    user: LoggedUser,
    p: dict[str, Any],
    sheet: str,
    path: str = "",
    data: dict[str, str] | None = None,
) -> Response:
    files = {"file": ("planilha.csv", sheet.encode("utf-8"), "text/csv")}
    url = f"{p['base']}/extraction-imports{path}"
    return await client.post(url, files=files, data=data or {}, headers=user.headers)


async def test_preview_suggests_columns_and_name_matches(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _setup(client, ana)
    r = await _send(client, ana, p, SHEET, "/preview")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["row_count"] == 5
    assert out["suggested_mapping"] == {
        "study": "estudo",
        "group": "grupo",
        "outcome": "desfecho",
        "timepoint": "momento",
        "n": "n",
        "mean": "media",
        "sd": "dp",
        "se": "ep",
        "source_location": "pagina",
    }
    groups = {g["text"]: g["match_id"] for g in out["groups"]}
    assert groups == {
        "< 5 anos": p["group"],
        ">= 5 anos": p["late"],
        "Precoce": None,
        "Tardio": None,
    }
    studies = {s["text"]: s["match_id"] for s in out["studies"]}
    assert studies["Ficticio A 2020"] == p["Ficticio A 2020"]
    assert studies["Desconhecido 1999"] is None


async def test_valid_studies_become_draft_extractions_and_bad_ones_are_skipped_whole(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _setup(client, ana)
    mapping = (await _send(client, ana, p, SHEET, "/preview")).json()["suggested_mapping"]
    form = {"mapping": json.dumps(mapping)}

    dry = (await _send(client, ana, p, SHEET, data={**form, "dry_run": "true"})).json()
    assert dry["imported_rows"] == 0
    by_label = {s["label"]: s for s in dry["studies"]}
    assert by_label["Ficticio A 2020"]["status"] == "ready"
    assert by_label["Ficticio B 2021"]["status"] == "skipped"
    codes = {(e["row"], e["code"]) for e in dry["errors"]}
    assert (5, "extraction.impossible.sd_not_positive") in codes
    assert (6, "extraction_import.unknown_study") in codes
    # A dry run writes nothing.
    listed = await client.get(
        f"{p['base']}/studies/{p['Ficticio A 2020']}/extractions", headers=ana.headers
    )
    assert listed.json() == []

    real = (await _send(client, ana, p, SHEET, data={**form, "dry_run": "false"})).json()
    a = next(s for s in real["studies"] if s["label"] == "Ficticio A 2020")
    assert a["status"] == "imported" and real["imported_rows"] == 2
    b = next(s for s in real["studies"] if s["label"] == "Ficticio B 2021")
    assert b["status"] == "skipped"
    assert (
        await client.get(
            f"{p['base']}/studies/{p['Ficticio B 2021']}/extractions", headers=ana.headers
        )
    ).json() == []

    detail = (
        await client.get(f"{p['base']}/extractions/{a['extraction_id']}", headers=ana.headers)
    ).json()
    assert detail["status"] == "draft" and detail["kind"] == "individual"
    arms = {arm["label"]: arm for arm in detail["arms"]}
    assert arms["< 5 anos"]["mapped_group_id"] == p["group"]
    assert arms["< 5 anos"]["n"] == 20
    row = next(x for x in detail["outcome_data"] if x["arm_id"] == arms["< 5 anos"]["id"])
    # "92,5" (comma decimal) is read as 92.5; the type comes from the column used.
    assert float(row["mean"]) == 92.5 and row["dispersion_type"] == "sd"
    assert row["source_location"] == "Tabela 2" and row["timepoint"] == "5 anos"

    # Running again never overwrites what is already there.
    again = (await _send(client, ana, p, SHEET, data={**form, "dry_run": "false"})).json()
    a = next(s for s in again["studies"] if s["label"] == "Ficticio A 2020")
    assert a["status"] == "skipped" and a["code"] == "extraction_import.already_extracted"


async def test_person_chooses_matches_and_rows_with_two_dispersions_are_refused(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _setup(client, ana)
    sheet = (
        HEADER
        + "Ficticio B 2021;Precoce;18;QI;;90;5;2,1;p. 4\n"
        + "Ficticio A 2020;Precoce;18;QI;5 anos;90;;2,1;p. 4\n"
        + "Ficticio A 2020;Tardio;22;QI;5 anos;1.234,5;;3;p. 4\n"
    )
    mapping = (await _send(client, ana, p, sheet, "/preview")).json()["suggested_mapping"]
    matches = {"groups": {"Precoce": p["group"], "Tardio": p["late"]}}
    data = {
        "mapping": json.dumps(mapping),
        "matches": json.dumps(matches),
        "dry_run": "false",
    }
    out = (await _send(client, ana, p, sheet, data=data)).json()
    assert {(e["row"], e["code"]) for e in out["errors"]} == {
        (2, "extraction_import.several_dispersions")
    }
    a = next(s for s in out["studies"] if s["label"] == "Ficticio A 2020")
    detail = (
        await client.get(f"{p['base']}/extractions/{a['extraction_id']}", headers=ana.headers)
    ).json()
    arms = {arm["label"]: arm["mapped_group_id"] for arm in detail["arms"]}
    assert arms == {"Precoce": p["group"], "Tardio": p["late"]}
    means = sorted(float(x["mean"]) for x in detail["outcome_data"])
    assert means == [90.0, 1234.5]  # "1.234,5": dot as thousands, comma as decimal


async def test_only_extractors_of_the_project_can_import(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, leo, out = await make_user("Ana"), await make_user("Leo"), await make_user("Fora")
    p = await _setup(client, ana)
    await _join(client, ana, leo, p["pid"], ["reader"])
    assert (await _send(client, leo, p, SHEET, "/preview")).status_code == 403
    assert (await _send(client, out, p, SHEET, "/preview")).status_code in (403, 404)
    r = await _send(client, out, p, SHEET, data={"mapping": "{}", "dry_run": "false"})
    assert r.status_code in (403, 404)
