"""Import of an existing consolidated risk-of-bias table (stage 2 step 6)."""

import json
from typing import Any

from httpx import AsyncClient

from tests.conftest import LoggedUser
from tests.test_consensus import MakeUser, _join
from tests.test_rob_assessments import _project

ROBVIS_CSV = (
    "Study,D1,D2,D3,D4,D5,D6,D7,Overall,Weight\n"
    "Coorte 2020,Low,Moderate,Grave,Critical,No information,low,Baixo,Serious risk,1\n"
    "Ensaio 2019,Low,Low,Low,Médio,Low,Low,Low,Low,1\n"
    "Desconhecido 2001,Low,Low,Low,Low,Low,Low,Low,Low,1\n"
)


async def _post(
    client: AsyncClient,
    user: LoggedUser,
    p: dict[str, Any],
    path: str,
    content: str,
    filename: str = "tabela.csv",
    **form: Any,
) -> Any:
    files = {"file": (filename, content.encode("utf-8"), "text/csv")}
    data = {k: (json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in form.items()}
    return await client.post(f"{p['rob']}/{path}", files=files, data=data, headers=user.headers)


async def test_robvis_table_is_imported_and_marked_as_imported(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    tool = (
        await client.post(
            f"{p['rob']}/tools", json={"template_key": "robins_i_2016"}, headers=ana.headers
        )
    ).json()

    preview = (
        await _post(client, ana, p, "imports/preview", ROBVIS_CSV, tool_id=tool["id"])
    ).json()
    assert preview["row_count"] == 3
    mapping = preview["suggested_mapping"]
    assert mapping["study"] == "Study" and mapping["overall"] == "Overall"
    assert mapping["d1"] == "D1" and mapping["d7"] == "D7"
    assert "Weight" not in mapping.values()

    r = await _post(client, bia, p, "imports", ROBVIS_CSV, tool_id=tool["id"], mapping=mapping)
    assert r.status_code == 403
    r = await _post(client, ana, p, "imports", ROBVIS_CSV, tool_id=tool["id"], mapping=mapping)
    assert r.json()["code"] == "rob.result_required"
    target = {"outcome_id": p["outcome"], "timepoint": "5 anos"}
    r = await _post(
        client,
        ana,
        p,
        "imports",
        ROBVIS_CSV,
        tool_id=tool["id"],
        mapping={"study": "Study"},
        **target,
    )
    assert r.json()["code"] == "rob_import.invalid_mapping"

    report = (
        await _post(
            client, ana, p, "imports", ROBVIS_CSV, tool_id=tool["id"], mapping=mapping, **target
        )
    ).json()
    assert report["dry_run"] is True and report["created"] == 0
    assert report["valid_rows"] == 1
    assert {(e["row"], e["field"], e["code"]) for e in report["errors"]} == {
        (3, "d4", "rob_import.unknown_value"),  # "Médio" is not a ROBINS-I level: never guessed
        (4, "study", "rob_import.unknown_study"),
    }

    report = (
        await _post(
            client,
            ana,
            p,
            "imports",
            ROBVIS_CSV,
            tool_id=tool["id"],
            mapping=mapping,
            dry_run="false",
            **target,
        )
    ).json()
    assert report["created"] == 1

    t = (
        await client.get(
            f"{p['rob']}/table?tool_id={tool['id']}&outcome_id={p['outcome']}&timepoint=5 anos",
            headers=bia.headers,
        )
    ).json()
    row = t["rows"][0]
    assert row["label"] == "Coorte 2020" and row["kind"] == "imported"
    # Portuguese, robvis and code spellings all map to the same levels.
    assert row["values"] == {
        "d1": "low",
        "d2": "moderate",
        "d3": "serious",
        "d4": "critical",
        "d5": "no_information",
        "d6": "low",
        "d7": "low",
    }
    assert row["overall"] == "serious"
    # The study now uses this instrument; the import never overwrites.
    study_tool = (
        await client.get(
            f"{p['rob']}/studies/{p['studies']['cohort_retrospective']}/tool", headers=ana.headers
        )
    ).json()
    assert study_tool["tool_id"] == tool["id"] and study_tool["confirmed"] is True
    again = (
        await _post(
            client, ana, p, "imports", ROBVIS_CSV, tool_id=tool["id"], mapping=mapping, **target
        )
    ).json()
    assert (2, "study", "rob_import.already_assessed") in {
        (e["row"], e["field"], e["code"]) for e in again["errors"]
    }


async def test_checklist_answers_and_other_instrument(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    nos = p["tools"]["nos_cohort"]
    # The trial already uses RoB 2: importing it with NOS is refused.
    await client.put(
        f"{p['rob']}/studies/{p['studies']['rct']}/tool",
        json={"tool_id": p["tools"]["rob2"]["id"]},
        headers=ana.headers,
    )
    content = (
        "Estudo;S1;S2;S3;S4;C1;O1;O2;O3;Geral;Justificativa\n"
        "Coorte 2020;1;1;1;0;2;1;1;0;Baixo;Regra do grupo: 7 estrelas\n"
        "Ensaio 2019;1;1;1;1;2;1;1;1;Baixo;\n"
    )
    mapping = {
        "study": "Estudo",
        "overall": "Geral",
        "overall_justification": "Justificativa",
        "selection.1": "S1",
        "selection.2": "S2",
        "selection.3": "S3",
        "selection.4": "S4",
        "comparability.1": "C1",
        "outcome.1": "O1",
        "outcome.2": "O2",
        "outcome.3": "O3",
    }
    report = (
        await _post(
            client, ana, p, "imports", content, tool_id=nos["id"], mapping=mapping, dry_run="false"
        )
    ).json()
    assert report["created"] == 1
    assert [(e["row"], e["code"]) for e in report["errors"]] == [(3, "rob_import.other_tool")]
    t = (await client.get(f"{p['rob']}/table?tool_id={nos['id']}", headers=ana.headers)).json()
    row = t["rows"][0]
    assert row["values"]["comparability.1"] == "stars_2_of_2"
    assert row["values"]["selection.4"] == "stars_0_of_1"
    assert row["overall"] == "low" and row["kind"] == "imported"
