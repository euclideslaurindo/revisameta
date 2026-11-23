"""PRISMA 2020 checklist (stage 5 step 7)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.prisma.checklist_items import CODES
from tests.test_consensus import MakeUser, _join, _project
from tests.test_search_import import _import

RIS = "TY  - JOUR\nTI  - FICTITIOUS record\nPY  - 2020\nER  - \n"


def test_the_template_has_every_prisma_2020_item() -> None:
    assert len(CODES) == 42 and len(set(CODES)) == 42
    assert CODES[0] == "1" and CODES[-1] == "27"
    for code in ("10a", "10b", "13f", "16b", "20d", "23d", "24c"):
        assert code in CODES


async def test_hints_status_location_and_roles(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    url = f"{p['base']}/prisma/checklist"
    out = (await client.get(url, headers=ana.headers)).json()
    rows = {r["code"]: r for r in out["rows"]}
    assert out["pending"] == 42 and not rows["7"]["has_data"]
    assert "BMJ 2021;372:n71" in out["citation"]
    await _import(client, ana, p, "busca.ris", RIS.encode(), strategy="(cranio*) AND age")
    rows = {r["code"]: r for r in (await client.get(url, headers=ana.headers)).json()["rows"]}
    # The system knows it has the search strategy, but never marks the item by itself.
    assert rows["6"]["has_data"] and rows["7"]["has_data"] and rows["7"]["status"] == "pending"

    body = {"status": "reported", "location": "Métodos, p. 4; Apêndice 1"}
    r = await client.put(f"{url}/7", headers=ana.headers, json=body)
    assert r.json()["location"] == "Métodos, p. 4; Apêndice 1" and r.json()["version"] == 1
    stale = await client.put(f"{url}/7", headers=ana.headers, json={"status": "pending"})
    assert stale.status_code == 409
    r = await client.put(
        f"{url}/7", headers=ana.headers, json={"status": "not_applicable", "version": 1}
    )
    assert r.json()["status"] == "not_applicable"
    assert (await client.put(f"{url}/99", headers=ana.headers, json=body)).status_code == 404
    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    assert (await client.put(f"{url}/1", headers=reader.headers, json=body)).status_code == 403
    audit = await session.scalars(
        select(AuditLog).where(AuditLog.entity == "prisma_checklist_items")
    )
    assert audit.first() is not None
    docx = await client.get(
        f"{p['base']}/prisma/checklist.docx", headers=reader.headers, params={"lang": "en"}
    )
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
