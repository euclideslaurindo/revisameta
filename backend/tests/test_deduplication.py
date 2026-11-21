"""Deduplication (stage 5 step 2; docs/validacao.md 11.2, "Deduplicação").

Every record is FICTITIOUS. The cases cover lesson L4: "Part 1" x "Part 2", erratum x
original article and titles that differ only at the end must NOT become duplicates;
the same DOI always does.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.references.dedup_rules import (
    DedupSettings,
    blocks,
    candidate,
    compare,
    first_author_surname,
)
from tests.test_consensus import MakeUser, _join, _project
from tests.test_search_import import _import

S = DedupSettings()
TITLE = "FICTITIOUS cognitive outcome after early cranial vault surgery in children"


def c(id_: int, title: str = TITLE, **kw: Any) -> Any:
    base: dict[str, Any] = {
        "authors": "Silva, Ana; Souza, Bruno",
        "year": 2019,
        "journal": "Journal of Made-Up Neurosurgery",
        "volume": "12",
        "pages": "101-110",
        "doi": None,
        "pmid": None,
    }
    base.update(kw)
    return candidate(id_, title, **base)


def kind(a: Any, b: Any, settings: DedupSettings = S) -> str | None:
    result = compare(a, b, settings)
    return result[0] if result else None


def test_same_doi_or_pmid_is_certain_even_with_different_titles() -> None:
    assert kind(c(1, doi="10.9999/x"), c(2, "Another title", doi="10.9999/x")) == "certain"
    assert kind(c(1, pmid="123"), c(2, "Other", pmid="123")) == "certain"


def test_probable_needs_every_criterion_together() -> None:
    # Punctuation, accents and case do not matter; the whole title is compared.
    assert kind(c(1), c(2, TITLE.upper() + ".")) == "probable"
    assert kind(c(1), c(2, year=2020)) is None  # different year
    assert kind(c(1), c(2, authors="Pereira, Carla")) is None  # different first author
    assert kind(c(1), c(2, volume="13")) is None  # both have volume and they differ
    # A field only one record has does not count against it; a missing year neither.
    assert kind(c(1), c(2, volume=None, year=None)) == "probable"


def test_titles_that_differ_at_the_end_are_not_duplicates() -> None:
    other = TITLE.replace("in children", "in adults with a long follow up")
    assert kind(c(1), c(2, other)) is None


def test_part_one_and_part_two_erratum_and_comment_are_related_never_duplicates() -> None:
    assert kind(c(1, TITLE + " Part 1"), c(2, TITLE + " Part 2")) == "related"
    assert kind(c(1), c(2, "Erratum: " + TITLE)) == "related"
    assert kind(c(1), c(2, "Comentário: " + TITLE)) == "related"
    assert kind(c(1), c(2, TITLE + " retracted")) == "related"


def test_threshold_is_configurable() -> None:
    near = TITLE.replace("cranial vault", "vault")  # score 0.943
    assert kind(c(1), c(2, near)) is None
    assert kind(c(1), c(2, near), DedupSettings(title_threshold=0.9)) == "probable"


def test_first_author_surname_in_the_usual_formats() -> None:
    assert first_author_surname("Silva, Ana; Souza, B") == "silva"
    assert first_author_surname("Ana Silva and Bruno Souza") == "silva"
    assert first_author_surname("Lima D") == "lima"
    assert first_author_surname("Gonçalves, J") == "goncalves"


def test_blocks_avoid_comparing_everything_with_everything() -> None:
    groups = blocks([c(1), c(2), c(3, authors="Other, X")])
    assert list(groups) == ["au:silva"] and len(groups["au:silva"]) == 2


# ---- Through the API ------------------------------------------------------------------

RIS_A = """TY  - JOUR
TI  - FICTITIOUS cognitive outcome after early cranial vault surgery in children
AU  - Silva, Ana
PY  - 2019
DO  - 10.9999/fict.dup
ER  -
TY  - JOUR
TI  - FICTITIOUS late repair: a cohort. Part 1
AU  - Lima, Daniel
PY  - 2018
ER  -
TY  - JOUR
TI  - FICTITIOUS late repair a cohort Part 2
AU  - Lima, Daniel
PY  - 2018
ER  -
TY  - JOUR
TI  - FICTITIOUS neurodevelopment and age at surgery
AU  - Rocha, Elisa
PY  - 2017
ER  -
"""

RIS_B = """TY  - JOUR
TI  - Fictitious cognitive outcome after early cranial-vault surgery in children.
AU  - Silva, A.
PY  - 2019
DO  - https://doi.org/10.9999/FICT.DUP
ER  -
TY  - JOUR
TI  - FICTITIOUS NEURODEVELOPMENT AND AGE AT SURGERY
AU  - Rocha, E
PY  - 2017
ER  -
"""


async def _setup(client: AsyncClient, make_user: MakeUser) -> tuple[Any, dict[str, Any]]:
    ana = await make_user()
    p = await _project(client, ana)
    await _import(client, ana, p, "pubmed.ris", RIS_A.encode())
    await _import(client, ana, p, "lilacs.ris", RIS_B.encode(), database="LILACS")
    return ana, p


async def test_run_decide_undo_and_report(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p = await _setup(client, make_user)
    base = f"{p['base']}/deduplication"
    run = (await client.post(f"{base}/run", headers=ana.headers)).json()
    assert run == {"certain": 1, "probable": 1, "related": 1, "new_pairs": 3}
    # Running again changes nothing.
    assert (await client.post(f"{base}/run", headers=ana.headers)).json()["new_pairs"] == 0
    pairs = {x["kind"]: x for x in (await client.get(f"{base}/pairs", headers=ana.headers)).json()}
    assert pairs["certain"]["criteria"]["same_doi"] is True
    probable = pairs["probable"]
    assert probable["criteria"]["first_author"] == "same" and probable["score"] >= 0.95
    report = (await client.get(f"{base}/report", headers=ana.headers)).json()
    assert report["imported"] == 6 and report["duplicates_removed"] == 0

    # Related pairs can never be confirmed as duplicates.
    related = pairs["related"]
    r = await client.post(
        f"{base}/pairs/{related['id']}",
        headers=ana.headers,
        json={"action": "confirm", "keep": "a", "version": related["version"]},
    )
    assert r.json()["code"] == "dedup.related_is_not_duplicate"

    r = await client.post(
        f"{base}/pairs/{probable['id']}",
        headers=ana.headers,
        json={"action": "confirm", "keep": "a", "version": probable["version"]},
    )
    assert r.status_code == 200, r.text
    confirmed = r.json()
    assert confirmed["status"] == "confirmed" and confirmed["kept_id"] == probable["a"]["id"]
    assert (await client.post(f"{base}/confirm-certain", headers=ana.headers)).json() == {
        "confirmed": 1
    }
    report = (await client.get(f"{base}/report", headers=ana.headers)).json()
    assert report["duplicates_removed"] == 2 and report["after_duplicates"] == 4
    refs = (await client.get(f"{p['base']}/references", headers=ana.headers)).json()["items"]
    assert sum(1 for x in refs if x["duplicate_of"]) == 2

    # Undo puts the record back (reversible, 7.2).
    r = await client.post(
        f"{base}/pairs/{probable['id']}",
        headers=ana.headers,
        json={"action": "undo", "version": confirmed["version"]},
    )
    assert r.json()["status"] == "pending"
    report = (await client.get(f"{base}/report", headers=ana.headers)).json()
    assert report["duplicates_removed"] == 1 and report["pending"]["probable"] == 1
    # Stale version: conflict, not an overwrite.
    r = await client.post(
        f"{base}/pairs/{probable['id']}",
        headers=ana.headers,
        json={"action": "reject", "version": probable["version"]},
    )
    assert r.status_code == 409
    csv = await client.get(f"{base}/report.csv", headers=ana.headers)
    assert csv.status_code == 200 and "same_doi=True" in csv.text


async def test_settings_and_roles(client: AsyncClient, make_user: MakeUser) -> None:
    ana, p = await _setup(client, make_user)
    base = f"{p['base']}/deduplication"
    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    assert (await client.post(f"{base}/run", headers=reader.headers)).status_code == 403
    assert (await client.get(f"{base}/pairs", headers=reader.headers)).status_code == 200
    reviewer = await make_user()
    await _join(client, ana, reviewer, p["pid"], ["reviewer"])
    body = {"title_threshold": 0.9}
    assert (
        await client.put(f"{base}/settings", headers=reviewer.headers, json=body)
    ).status_code == 403
    r = await client.put(f"{base}/settings", headers=ana.headers, json=body)
    assert r.json() == body
    assert (await client.get(f"{base}/settings", headers=reader.headers)).json() == body
    bad = await client.put(f"{base}/settings", headers=ana.headers, json={"title_threshold": 0.5})
    assert bad.status_code == 422
