"""Export of extracted data (docs/validacao.md 11.2: never export blank in silence)."""

import csv
import io
from typing import Any

from httpx import AsyncClient
from openpyxl import load_workbook

from tests.conftest import FakeR, LoggedUser
from tests.test_consensus import MakeUser, _join, _project
from tests.test_review import _checked_consensus


async def _setup(
    client: AsyncClient, make_user: MakeUser
) -> tuple[dict[str, Any], LoggedUser, ...]:
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["extractor"])
    await _checked_consensus(client, ana, (bia, caio), p)
    # A second study nobody extracted yet.
    await client.post(
        f"{p['base']}/studies",
        json={"label": "Sem dados 2019", "design": "other", "reference": {"title": "Outro"}},
        headers=ana.headers,
    )
    return p, ana, bia, caio


async def _export(client: AsyncClient, user: LoggedUser, p: dict[str, Any], **params: Any) -> Any:
    query = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
    return await client.get(f"{p['base']}/exports/extraction", params=query, headers=user.headers)


async def test_missing_studies_are_never_left_out_silently(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    p, ana, *_ = await _setup(client, make_user)
    status = (
        await client.get(f"{p['base']}/exports/extraction/status", headers=ana.headers)
    ).json()
    assert status["total"] == 2 and status["ready"] == 1
    assert [(m["label"], m["reason"]) for m in status["missing"]] == [
        ("Sem dados 2019", "no_extraction")
    ]

    r = await _export(client, ana, p)
    assert r.status_code == 409
    assert r.json()["code"] == "export.incomplete"

    r = await _export(client, ana, p, acknowledge_missing=True)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    assert "_extracao_" in r.headers["content-disposition"]
    book = load_workbook(io.BytesIO(r.content), read_only=True)
    assert book.sheetnames == ["Leia-me", "Estudos", "Grupos", "Dados", "Alertas justificados"]
    readme = [
        [c for c in row if c is not None] for row in book["Leia-me"].iter_rows(values_only=True)
    ]
    assert ["  Sem dados 2019", "sem extração"] in readme
    assert any("Consenso" in str(row) for row in readme)


async def test_xlsx_keeps_numbers_as_numbers_in_the_output_language(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    p, ana, *_ = await _setup(client, make_user)
    r = await _export(client, ana, p, acknowledge_missing=True, lang="en")
    book = load_workbook(io.BytesIO(r.content), read_only=True)
    assert book.sheetnames[3] == "Data"
    rows = list(book["Data"].iter_rows(values_only=True))
    header = rows[0]
    assert header[:3] == ("Study", "Data origin", "Extractor")
    early = next(row for row in rows[1:] if row[header.index("Group in the article")] == "Precoce")
    assert early[header.index("SD")] == 11.3  # the value decided in the consensus
    assert early[header.index("Mean")] == 92.5
    assert early[header.index("Dispersion type")] == "SD"
    assert early[header.index("Data origin")] == "consensus"
    arms = list(book["Groups"].iter_rows(values_only=True))
    assert {row[3] for row in arms[1:]} == {"Precoce", "Tardio"}


async def test_csv_for_excel_and_for_r(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    p, ana, *_ = await _setup(client, make_user)
    r = await _export(client, ana, p, file_format="csv", acknowledge_missing=True)
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM so Excel reads accents
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    header = rows[0]
    assert header[0] == "Estudo"
    early = next(row for row in rows[1:] if row[header.index("Grupo no artigo")] == "Precoce")
    assert early[header.index("DP")] == "11,3"
    assert early[header.index("Média")] == "92,5"

    r = await _export(client, ana, p, file_format="csv", csv_style="r", acknowledge_missing=True)
    assert not r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8")), delimiter=","))
    header = rows[0]
    early = next(row for row in rows[1:] if row[header.index("Grupo no artigo")] == "Precoce")
    assert early[header.index("DP")] == "11.3"


async def test_individual_extractions_are_marked_pre_consensus_and_admin_only(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    p, ana, bia, _ = await _setup(client, make_user)
    r = await _export(client, bia, p, mode="individual", acknowledge_missing=True)
    assert r.status_code == 403

    r = await _export(client, ana, p, mode="individual", acknowledge_missing=True)
    assert r.status_code == 200, r.text
    assert "pre-consenso" in r.headers["content-disposition"]
    rows = list(
        load_workbook(io.BytesIO(r.content), read_only=True)["Dados"].iter_rows(values_only=True)
    )
    header = rows[0]
    sds = {
        (row[header.index("Extrator")], row[header.index("DP")])
        for row in rows[1:]
        if row[header.index("Grupo no artigo")] == "Precoce"
    }
    assert sds == {("Bia", 11.2), ("Caio", 11.3)}
    assert {row[header.index("Origem dos dados")] for row in rows[1:]} == {"pré-consenso"}


async def test_nothing_to_export_is_an_error_not_a_blank_file(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    r = await _export(client, ana, p, acknowledge_missing=True)
    assert r.status_code == 409
    assert r.json()["code"] == "export.empty"


async def test_readers_can_export_the_consensus(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    p, ana, *_ = await _setup(client, make_user)
    leo = await make_user("Leo")
    await _join(client, ana, leo, p["pid"], ["reader"])
    r = await _export(client, leo, p, file_format="csv", acknowledge_missing=True)
    assert r.status_code == 200
