import io
import json
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.modules.studies.importer import parse_design, suggest_mapping
from app.modules.studies.schemas import normalize_doi, normalize_pmid
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _project(client: AsyncClient, user: LoggedUser) -> str:
    r = await client.post("/api/v1/projects", json={"title": "P"}, headers=user.headers)
    return str(r.json()["id"])


def _study(label: str = "Ballet 2025", **ref: Any) -> dict[str, Any]:
    return {
        "label": label,
        "design": "cohort_retrospective",
        "reference": {"title": "Artigo fictício", "year": 2025, **ref},
    }


# ---- Unit: normalization ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/ABC.123", "10.1000/abc.123"),
        (" https://doi.org/10.1000/xyz ", "10.1000/xyz"),
        ("doi: 10.1016/J.X.2020", "10.1016/j.x.2020"),
        ("", None),
        (None, None),
    ],
)
def test_doi_normalization(raw: str | None, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


def test_invalid_doi_and_pmid_are_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_doi("not a doi")
    with pytest.raises(ValueError):
        normalize_pmid("12ab")
    assert normalize_pmid("31415926.0") == "31415926"


def test_design_and_mapping_hints_in_both_languages() -> None:
    assert parse_design("Coorte retrospectiva") == "cohort_retrospective"
    assert parse_design("Case-control") == "case_control"
    assert parse_design("ECR") == "rct"
    assert parse_design("bla") is None
    mapping = suggest_mapping(["Estudo", "Título", "Autores", "Ano", "DOI", "Desenho", "Outra"])
    assert mapping == {
        "label": "Estudo",
        "title": "Título",
        "authors": "Autores",
        "year": "Ano",
        "doi": "DOI",
        "design": "Desenho",
    }


# ---- Studies and reports ------------------------------------------------------------


async def test_create_study_with_primary_report(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/studies",
        json=_study(doi="https://doi.org/10.1000/AAA"),
        headers=ana.headers,
    )
    assert r.status_code == 201
    study = r.json()
    assert study["design"] == "cohort_retrospective"
    assert len(study["reports"]) == 1
    assert study["reports"][0]["is_primary"] is True
    assert study["reports"][0]["reference"]["doi"] == "10.1000/aaa"


async def test_same_study_or_doi_cannot_be_registered_twice(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    base = f"/api/v1/projects/{pid}/studies"
    await client.post(base, json=_study(doi="10.1000/aaa"), headers=ana.headers)
    r = await client.post(base, json=_study("ballet 2025"), headers=ana.headers)
    assert r.json()["code"] == "study.duplicate_label"
    r = await client.post(
        base, json=_study("Outro 2024", doi="DOI:10.1000/AAA"), headers=ana.headers
    )
    assert r.json()["code"] == "study.duplicate_doi"


async def test_several_articles_of_the_same_patients(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    base = f"/api/v1/projects/{pid}/studies"
    study = (await client.post(base, json=_study(), headers=ana.headers)).json()

    r = await client.post(
        f"{base}/{study['id']}/reports",
        json={"reference": {"title": "Seguimento de 10 anos", "year": 2027}, "is_primary": True},
        headers=ana.headers,
    )
    reports = r.json()["reports"]
    assert len(reports) == 2
    assert [rep["is_primary"] for rep in reports] == [True, False]
    assert reports[0]["reference"]["title"] == "Seguimento de 10 anos"

    r = await client.delete(f"{base}/{study['id']}/reports/{reports[0]['id']}", headers=ana.headers)
    remaining = r.json()["reports"]
    assert len(remaining) == 1
    assert remaining[0]["is_primary"] is True
    r = await client.delete(
        f"{base}/{study['id']}/reports/{remaining[0]['id']}", headers=ana.headers
    )
    assert r.json()["code"] == "study.last_report"


async def test_merge_two_studies_that_are_the_same_cohort(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    base = f"/api/v1/projects/{pid}/studies"
    first = (await client.post(base, json=_study("Silva 2020"), headers=ana.headers)).json()
    second = (await client.post(base, json=_study("Silva 2022"), headers=ana.headers)).json()
    r = await client.post(
        f"{base}/{first['id']}/merge", json={"other_study_id": second["id"]}, headers=ana.headers
    )
    assert len(r.json()["reports"]) == 2
    listed = (await client.get(base, headers=ana.headers)).json()
    assert [s["label"] for s in listed] == ["Silva 2020"]
    r = await client.post(
        f"{base}/{first['id']}/merge", json={"other_study_id": first["id"]}, headers=ana.headers
    )
    assert r.status_code == 422


async def test_edit_study_and_reference(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    study = (
        await client.post(f"/api/v1/projects/{pid}/studies", json=_study(), headers=ana.headers)
    ).json()
    r = await client.patch(
        f"/api/v1/projects/{pid}/studies/{study['id']}",
        json={"version": 1, "design": "rct", "notes": "Dados no material suplementar"},
        headers=ana.headers,
    )
    assert r.json()["design"] == "rct"
    ref = study["reports"][0]["reference"]
    r = await client.patch(
        f"/api/v1/projects/{pid}/references/{ref['id']}",
        json={"version": 1, "pmid": "123456"},
        headers=ana.headers,
    )
    assert r.json()["pmid"] == "123456"
    stale = await client.patch(
        f"/api/v1/projects/{pid}/references/{ref['id']}",
        json={"version": 1, "pmid": "1"},
        headers=ana.headers,
    )
    assert stale.status_code == 409


async def test_delete_is_soft_and_admin_only(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    extractor = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": ["extractor"]}, headers=ana.headers
    )
    token = r.json()["link"].split("token=")[1]
    await client.post(f"/api/v1/invitations/{token}/accept", headers=extractor.headers)

    base = f"/api/v1/projects/{pid}/studies"
    study = (
        await client.post(base, json=_study(doi="10.1000/x"), headers=extractor.headers)
    ).json()
    assert study["label"] == "Ballet 2025"
    assert (
        await client.delete(f"{base}/{study['id']}", headers=extractor.headers)
    ).status_code == 403
    assert (await client.delete(f"{base}/{study['id']}", headers=ana.headers)).status_code == 204
    assert (await client.get(base, headers=ana.headers)).json() == []
    # The DOI is free again after the study is deleted.
    r = await client.post(base, json=_study(doi="10.1000/x"), headers=ana.headers)
    assert r.status_code == 201


async def test_readers_cannot_register_studies(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    reader = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": ["reader"]}, headers=ana.headers
    )
    await client.post(
        f"/api/v1/invitations/{r.json()['link'].split('token=')[1]}/accept", headers=reader.headers
    )
    r = await client.post(f"/api/v1/projects/{pid}/studies", json=_study(), headers=reader.headers)
    assert r.status_code == 403


# ---- Import -------------------------------------------------------------------------

CSV_PT = (
    "Estudo;Título;Autores;Ano;DOI;Desenho\n"
    "Ballet 2025;Cirurgia precoce (fictício);Ballet A, Lima B;2025;10.1000/a1;"
    "Coorte retrospectiva\n"
    ";Sem nome mas com autor;Souza C;2021;;Caso-controle\n"
    "Lima 2019;;Lima D;2019;;\n"
    "Costa 2018;Ano errado;Costa E;dois mil;;\n"
    "Ballet 2025;Repetido no arquivo;Ballet A;2025;;\n"
    "Melo 2020;DOI repetido;Melo F;2020;10.1000/A1;\n"
    "Reis 2017;Desenho estranho;Reis G;2017;;quase experimento\n"
    ";;;;;\n"
)


def _files(name: str, content: bytes) -> dict[str, tuple[str, bytes]]:
    return {"file": (name, content)}


async def test_preview_suggests_mapping_and_shows_sample(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/study-imports/preview",
        files=_files("lista.csv", CSV_PT.encode("utf-8-sig")),
        headers=ana.headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["columns"][:2] == ["Estudo", "Título"]
    assert body["row_count"] == 7
    assert body["sample"][0][0] == "Ballet 2025"
    assert body["suggested_mapping"]["title"] == "Título"


async def test_import_reports_each_bad_row_and_imports_the_rest(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    mapping = {
        "label": "Estudo",
        "title": "Título",
        "authors": "Autores",
        "year": "Ano",
        "doi": "DOI",
        "design": "Desenho",
    }
    url = f"/api/v1/projects/{pid}/study-imports"
    form = {"mapping": json.dumps(mapping), "dry_run": "true"}
    dry = await client.post(
        url, data=form, files=_files("lista.csv", CSV_PT.encode()), headers=ana.headers
    )
    report = dry.json()
    assert report["dry_run"] is True
    assert report["total_rows"] == 7
    assert report["valid_rows"] == 2
    assert report["created"] == 0
    codes = {(e["row"], e["code"]) for e in report["errors"]}
    assert codes == {
        (4, "import.missing_title"),
        (5, "import.invalid_year"),
        (6, "import.duplicate_label_in_file"),
        (7, "import.duplicate_doi_in_file"),
        (8, "import.invalid_design"),
    }
    assert (await client.get(f"/api/v1/projects/{pid}/studies", headers=ana.headers)).json() == []

    form["dry_run"] = "false"
    real = await client.post(
        url, data=form, files=_files("lista.csv", CSV_PT.encode()), headers=ana.headers
    )
    assert real.json()["created"] == 2
    studies = (await client.get(f"/api/v1/projects/{pid}/studies", headers=ana.headers)).json()
    labels = sorted(s["label"] for s in studies)
    assert labels == ["Ballet 2025", "Souza 2021"]  # label built from first author + year
    ballet = next(s for s in studies if s["label"] == "Ballet 2025")
    assert ballet["design"] == "cohort_retrospective"
    assert ballet["reports"][0]["reference"]["doi"] == "10.1000/a1"

    again = await client.post(
        url, data=form, files=_files("lista.csv", CSV_PT.encode()), headers=ana.headers
    )
    again_codes = {e["code"] for e in again.json()["errors"]}
    assert "study.duplicate_label" in again_codes
    assert again.json()["created"] == 0


async def test_import_xlsx_and_comma_csv(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    wb = Workbook()
    sheet = wb.active
    assert sheet is not None
    sheet.append(["Study", "Title", "Year", "PMID"])
    sheet.append(["Rossi 2016", "Fictional cohort", 2016, 27182818])
    buffer = io.BytesIO()
    wb.save(buffer)
    url = f"/api/v1/projects/{pid}/study-imports"
    mapping = json.dumps({"label": "Study", "title": "Title", "year": "Year", "pmid": "PMID"})
    r = await client.post(
        url,
        data={"mapping": mapping, "dry_run": "false"},
        files=_files("list.xlsx", buffer.getvalue()),
        headers=ana.headers,
    )
    assert r.json()["created"] == 1, r.json()
    study = (await client.get(f"/api/v1/projects/{pid}/studies", headers=ana.headers)).json()[0]
    assert study["design"] == "other"
    assert study["reports"][0]["reference"]["pmid"] == "27182818"

    csv_en = 'Title,Authors,Year\nAnother cohort,"Ng K, Wu L",2015\n'.encode("cp1252")
    r = await client.post(
        url,
        data={
            "mapping": json.dumps({"title": "Title", "authors": "Authors", "year": "Year"}),
            "dry_run": "false",
        },
        files=_files("list.csv", csv_en),
        headers=ana.headers,
    )
    assert r.json()["created"] == 1
    labels = [
        s["label"]
        for s in (await client.get(f"/api/v1/projects/{pid}/studies", headers=ana.headers)).json()
    ]
    assert "Ng 2015" in labels


@pytest.mark.parametrize(
    ("name", "content", "mapping", "code"),
    [
        ("lista.pdf", b"%PDF", {"title": "x"}, "import.unsupported_format"),
        ("lista.xlsx", b"not a zip", {"title": "x"}, "import.unsupported_format"),
        ("lista.csv", b"", {"title": "x"}, "import.empty_file"),
        ("lista.csv", b"A;B\n1;2\n", {"label": "A"}, "import.invalid_mapping"),
        ("lista.csv", b"A;B\n1;2\n", {"title": "Nope"}, "import.invalid_mapping"),
        ("lista.csv", b"A;B\n1;2\n", {"title": "A", "color": "B"}, "import.invalid_mapping"),
    ],
)
async def test_bad_files_and_mappings_get_clear_errors(
    client: AsyncClient,
    make_user: MakeUser,
    name: str,
    content: bytes,
    mapping: dict[str, str],
    code: str,
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/study-imports",
        data={"mapping": json.dumps(mapping)},
        files=_files(name, content),
        headers=ana.headers,
    )
    assert r.status_code in (413, 415, 422)
    assert r.json()["code"] == code


async def test_mapping_must_be_json(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/study-imports",
        data={"mapping": "{nope"},
        files=_files("a.csv", b"A\n1\n"),
        headers=ana.headers,
    )
    assert r.json()["code"] == "import.invalid_mapping"
