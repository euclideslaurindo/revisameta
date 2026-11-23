"""Bibliography of the included studies (stage 6 step 5). Records are FICTITIOUS."""

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.studies.models import Reference
from tests.test_consensus import MakeUser, _project

REF = {
    "title": "FICTITIOUS cohort of early surgery",
    "authors": (
        "Silva, João Pedro; Souza, Ana; Lima, Bia; Reis, Caio; Dias, Davi; Melo, Eva; Rocha, Fabio"
    ),
    "year": 2021,
    "journal": "Fict J Neurosurg",
    "doi": "10.0000/fict.2021.1",
}


async def test_ris_bibtex_and_vancouver(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    p = await _project(client, ana)  # one study whose reference has only a title
    url = f"{p['base']}/exports/bibliography"
    r = await client.post(
        f"{p['base']}/studies",
        headers=ana.headers,
        json={"label": "Silva 2021", "design": "cohort_prospective", "reference": REF},
    )
    assert r.status_code == 201, r.text
    # Volume, issue and pages come from search imports; set them as an import would.
    await session.execute(
        update(Reference)
        .where(Reference.doi == REF["doi"])
        .values(volume="12", issue="3", pages="101-110")
    )
    await session.commit()

    st = (await client.get(f"{url}/status", headers=ana.headers)).json()
    assert st["records"] == 2 and st["incomplete"] == ["Ficticio 2020"]

    ris = (await client.get(url, headers=ana.headers, params={"file_format": "ris"})).text
    assert "AU  - Silva, João Pedro" in ris and "DO  - 10.0000/fict.2021.1" in ris
    assert ris.count("ER  - ") == 2

    bib = await client.get(url, headers=ana.headers, params={"file_format": "bibtex"})
    assert bib.headers["content-disposition"].count(".bib") == 2
    assert "@article{silva2021," in bib.text and "pages = {101--110}" in bib.text
    assert "author = {Silva, João Pedro and Souza, Ana" in bib.text

    van = (await client.get(url, headers=ana.headers, params={"file_format": "vancouver"})).text
    line = next(x for x in van.splitlines() if "early surgery" in x)
    assert line.endswith(
        "Silva JP, Souza A, Lima B, Reis C, Dias D, Melo E, et al. FICTITIOUS cohort of "
        "early surgery. Fict J Neurosurg. 2021;12(3):101-110. doi:10.0000/fict.2021.1"
    )


async def test_empty_project_gets_a_clear_message(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = (
        await client.post("/api/v1/projects", json={"title": "Vazio"}, headers=ana.headers)
    ).json()["id"]
    r = await client.get(f"/api/v1/projects/{pid}/exports/bibliography", headers=ana.headers)
    assert r.status_code == 409 and r.json()["code"] == "exports.bibliography_empty"
