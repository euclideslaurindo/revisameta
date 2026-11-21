"""Search import (stage 5 step 1): RIS, PubMed .nbib, BibTeX and CSV.

Every record below is FICTITIOUS (made-up titles, authors and identifiers).
"""

import io
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.references.parsers import (
    Record,
    RecordError,
    detect_format,
    read_bibtex,
    read_csv,
    read_nbib,
    read_ris,
)
from app.modules.studies.models import Reference
from tests.test_consensus import MakeUser, _join, _project

RIS = """TY  - JOUR
TI  - FICTITIOUS cognitive outcome after early surgery
AU  - Silva, Ana
AU  - Souza, Bruno
PY  - 2019
DA  - 2018/05/01
JO  - Journal of Made-Up Neurosurgery
VL  - 12
IS  - 3
SP  - 101
EP  - 110
DO  - https://doi.org/10.9999/FICT.0001
AB  - First line of the abstract
  that continues here.
KW  - craniosynostosis
KW  - cognition
ER  -

TY  - JOUR
AU  - Sem Titulo, Carla
PY  - 2020
ER  -

TY  - JOUR
TI  - FICTITIOUS second record
PY  - 2021
DO  - not a doi at all
ER  -
"""

NBIB = """PMID- 99999901
TI  - FICTITIOUS late versus early surgery: a cohort
      with a title on two lines.
FAU - Lima, Daniel
AU  - Lima D
DP  - 2017 Mar
JT  - Made-Up Pediatric Journal
VI  - 4
IP  - 2
PG  - 55-60
LID - 10.9999/fict.0002 [doi]
AB  - Abstract text.
MH  - Child

PMID- 99999902
TI  - FICTITIOUS another one.
DP  - 2016
"""

BIB = """% exported by a FICTITIOUS manager
@string{jn = "Made-Up Journal"}
@article{key1,
  title = {{FICTITIOUS} outcomes of surgery \\& follow-up},
  author = {Rocha, Elisa and Prado, Fabio},
  year = 2015,
  journal = "Made-Up Journal",
  pages = {1--9},
  doi = {10.9999/fict.0003},
  keywords = {surgery; age}
}
@comment{ignored}
@inproceedings{key2, title={FICTITIOUS congress abstract}, year={2014}}
"""

CSV = (
    "Título;Autores;Ano;DOI;Revista\n"
    'FICTITIOUS spreadsheet record;"Gomes, Hugo; Nunes, Iara";2013;10.9999/fict.0004;Made-Up\n'
    ";Sem titulo;2012;;\n"
)


def _records(items: list[Any]) -> list[Record]:
    return [i for i in items if isinstance(i, Record)]


def test_ris_reader() -> None:
    items = list(read_ris(io.StringIO(RIS)))
    first = items[0]
    assert isinstance(first, Record)
    v = first.values
    assert v["title"] == "FICTITIOUS cognitive outcome after early surgery"
    assert v["authors"] == "Silva, Ana; Souza, Bruno"
    assert v["year"] == 2019  # PY wins over DA
    assert v["doi"] == "10.9999/fict.0001" and v["pages"] == "101-110"
    assert v["abstract"] == "First line of the abstract that continues here."
    assert v["keywords"] == "craniosynostosis; cognition"
    assert items[1] == RecordError(2, "import.no_title")
    # A bad DOI does not lose the record: it is imported with the DOI empty and a warning.
    third = items[2]
    assert isinstance(third, Record) and third.values["doi"] is None
    assert third.warnings == ["import.bad_doi"]


def test_nbib_reader() -> None:
    items = _records(list(read_nbib(io.StringIO(NBIB))))
    assert len(items) == 2
    v = items[0].values
    assert v["pmid"] == "99999901" and v["doi"] == "10.9999/fict.0002"
    assert v["title"] == "FICTITIOUS late versus early surgery: a cohort with a title on two lines."
    assert v["authors"] == "Lima, Daniel" and v["year"] == 2017 and v["pages"] == "55-60"
    assert items[1].values["year"] == 2016


def test_bibtex_reader() -> None:
    items = _records(list(read_bibtex(io.StringIO(BIB))))
    assert [i.values["title"] for i in items] == [
        "FICTITIOUS outcomes of surgery & follow-up",
        "FICTITIOUS congress abstract",
    ]
    v = items[0].values
    assert v["authors"] == "Rocha, Elisa; Prado, Fabio" and v["year"] == 2015
    assert v["pages"] == "1-9" and v["doi"] == "10.9999/fict.0003"
    assert v["journal"] == "Made-Up Journal" and v["keywords"] == "surgery; age"


def test_csv_reader_with_semicolons_and_accented_headers() -> None:
    items = list(read_csv(io.StringIO(CSV)))
    first = items[0]
    assert isinstance(first, Record)
    assert first.values["title"] == "FICTITIOUS spreadsheet record"
    assert first.values["year"] == 2013 and first.values["doi"] == "10.9999/fict.0004"
    assert first.values["authors"] == "Gomes, Hugo; Nunes, Iara"
    assert items[1] == RecordError(2, "import.no_title")


def test_format_detection() -> None:
    assert detect_format("busca.RIS", "") == "ris"
    assert detect_format("pubmed.txt", "PMID- 1\n") == "nbib"
    assert detect_format("export", "﻿@article{x,") == "bibtex"
    assert detect_format("notes.txt", "hello") is None


# ---- Through the API (the worker runs inline in tests) ----------------------------------


async def _import(
    client: AsyncClient, user: Any, p: dict[str, Any], name: str, content: bytes, **form: str
) -> Any:
    data = {"database": "PubMed", "search_date": "2026-11-01", **form}
    return await client.post(
        f"{p['base']}/searches",
        headers=user.headers,
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )


async def test_import_records_the_search_and_reports_bad_records(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    r = await _import(client, ana, p, "busca.ris", RIS.encode(), strategy="(surgery) AND age")
    assert r.status_code == 201, r.text
    search = r.json()
    job = (await client.get(f"{p['base']}/jobs/{search['job_id']}", headers=ana.headers)).json()
    assert job["status"] == "succeeded" and job["result"]["records"] == 2
    detail = (await client.get(f"{p['base']}/searches/{search['id']}", headers=ana.headers)).json()
    assert detail["status"] == "done" and detail["strategy"] == "(surgery) AND age"
    assert detail["record_count"] == 2 and detail["error_count"] == 1
    assert detail["warning_count"] == 1
    assert detail["errors"] == [
        {"number": 2, "code": "import.no_title", "skipped": True},
        {"number": 3, "code": "import.bad_doi", "skipped": False},
    ]
    refs = (await client.get(f"{p['base']}/references", headers=ana.headers)).json()
    assert refs["total"] == 2 and refs["items"][0]["record_number"] == 1
    # The search itself is audited once (not every reference).
    audit = await session.scalars(select(AuditLog).where(AuditLog.entity == "searches"))
    assert audit.first() is not None


async def test_same_doi_twice_is_kept_for_deduplication(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    for name in ("pubmed.nbib", "again.nbib"):
        r = await _import(client, ana, p, name, NBIB.encode())
        assert r.status_code == 201
    refs = (await client.get(f"{p['base']}/references", headers=ana.headers)).json()
    assert refs["total"] == 4  # nothing removed in silence: deduplication decides later


async def test_windows_1252_files_and_other_formats(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    r = await _import(client, ana, p, "planilha.csv", CSV.encode("cp1252"))
    search = r.json()
    refs = (
        await client.get(
            f"{p['base']}/references", params={"search_id": search["id"]}, headers=ana.headers
        )
    ).json()
    assert refs["items"][0]["title"] == "FICTITIOUS spreadsheet record"
    r = await _import(client, ana, p, "lib.bib", BIB.encode())
    assert r.status_code == 201
    r = await _import(client, ana, p, "notes.txt", b"just text")
    assert r.json()["code"] == "import.unknown_format"
    r = await _import(client, ana, p, "empty.ris", b"")
    assert r.status_code == 422


async def test_large_search_is_read_in_batches_with_pagination(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    n = 20_000
    content = "".join(
        f"TY  - JOUR\nTI  - FICTITIOUS record {i}\nPY  - 2020\nER  - \n" for i in range(n)
    ).encode()
    r = await _import(client, ana, p, "big.ris", content)
    assert r.status_code == 201
    count = await session.scalar(
        select(func.count()).select_from(Reference).where(Reference.search_id == r.json()["id"])
    )
    assert count == n
    page = (
        await client.get(f"{p['base']}/references", params={"limit": 200}, headers=ana.headers)
    ).json()
    assert page["total"] == n and len(page["items"]) == 200 and page["next_cursor"]
    nxt = (
        await client.get(
            f"{p['base']}/references",
            params={"limit": 200, "after": page["next_cursor"]},
            headers=ana.headers,
        )
    ).json()
    assert nxt["items"][0]["record_number"] == 201


async def test_roles_and_soft_delete(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    assert (await _import(client, reader, p, "x.ris", RIS.encode())).status_code == 403
    reviewer = await make_user()
    await _join(client, ana, reviewer, p["pid"], ["reviewer"])
    search = (await _import(client, reviewer, p, "x.ris", RIS.encode())).json()
    url = f"{p['base']}/searches/{search['id']}"
    assert (await client.delete(url, headers=reader.headers)).status_code == 403
    assert (await client.delete(url, headers=reviewer.headers)).status_code == 204
    assert (await client.get(url, headers=ana.headers)).status_code == 404
    refs = (await client.get(f"{p['base']}/references", headers=ana.headers)).json()
    assert refs["total"] == 0
