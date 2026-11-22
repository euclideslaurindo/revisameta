"""PRISMA 2020 flow diagram (stage 5 step 6): counts from the whole flow, manual
adjustments with justification, and the figure drawn by the real R service.
Every record is FICTITIOUS.
"""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.studies.models import Reference
from tests.test_consensus import MakeUser, _join
from tests.test_full_text import _ft, _reasons
from tests.test_screening import _decide, _queue, _team
from tests.test_search_import import _import

NL = chr(10)
DUP = """TY  - JOUR
TI  - FICTITIOUS screening record 1
AB  - Abstract 1.
PY  - 2020
ER  -
"""


async def _flow(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> tuple[Any, Any, Any, dict[str, Any]]:
    """6 records from PubMed + 1 duplicate from LILACS; 4 pass title/abstract, 1 excluded,
    1 pending; at full text 1 included, 1 excluded (population), 1 not retrieved, 1 pending."""
    ana, bia, caio, p = await _team(client, make_user)
    await _import(client, ana, p, "lilacs.ris", DUP.encode(), database="LILACS")
    # The duplicate confirmation itself is tested in test_deduplication.py; here the
    # LILACS record is marked as a duplicate of the PubMed one, as a confirmation does.
    rows = list(
        await session.scalars(
            select(Reference)
            .where(Reference.project_id == uuid.UUID(p["pid"]))
            .order_by(Reference.id)
        )
    )
    rows[-1].duplicate_of = rows[0].id
    await session.commit()
    refs = [i["reference"]["id"] for i in (await _queue(client, bia, p, limit=50))["items"]]
    assert len(refs) == 6
    for ref in refs[:4]:
        await _decide(client, bia, p, ref, "include")
        await _decide(client, caio, p, ref, "include")
    await _decide(client, bia, p, refs[4], "exclude")
    await _decide(client, caio, p, refs[4], "exclude")
    reasons = {r["key"]: r["id"] for r in await _reasons(client, ana, p)}
    for user in (bia, caio):
        await _ft(client, user, p, refs[0], "include")
        await _ft(client, user, p, refs[1], "exclude", reasons["wrong_population"])
        await _ft(client, user, p, refs[2], "exclude", reasons["full_text_unavailable"])
    return ana, bia, caio, p


async def test_counts_follow_the_whole_flow(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, _, _, p = await _flow(client, make_user, session)
    c = (await client.get(f"{p['base']}/prisma/counts", headers=ana.headers)).json()
    assert c["identified"] == [{"database": "LILACS", "n": 1}, {"database": "PubMed", "n": 6}]
    v = c["values"]
    assert v["identified_total"] == 7 and v["duplicates_removed"] == 1
    assert v["records_screened"] == 6 and v["records_excluded"] == 1
    assert v["reports_sought"] == 4 and v["reports_not_retrieved"] == 1
    assert v["reports_assessed"] == 2 and v["reports_excluded_total"] == 1
    assert [(r["key"], r["n"]) for r in c["reports_excluded"]] == [("wrong_population", 1)]
    assert c["pending"] == {"title_abstract": 1, "full_text": 1}
    assert c["warnings"] == ["title_abstract_pending", "full_text_pending"]


async def test_manual_adjustment_needs_a_justification_and_is_audited(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, bia, _, p = await _flow(client, make_user, session)
    url = f"{p['base']}/prisma/adjustments/studies_included"
    assert (await client.put(url, headers=bia.headers, json={"value": 6})).status_code == 403
    r = await client.put(url, headers=ana.headers, json={"value": 6})
    assert r.json()["code"] == "prisma.justification_required"
    body = {"value": 6, "justification": "Imported only the final list of studies"}
    c = (await client.put(url, headers=ana.headers, json=body)).json()
    assert c["values"]["studies_included"] == 6 and c["computed"]["studies_included"] == 1
    assert c["adjusted"]["studies_included"]["justification"].startswith("Imported")
    audit = await session.scalars(select(AuditLog).where(AuditLog.entity == "prisma_adjustments"))
    assert audit.first() is not None
    c = (await client.put(url, headers=ana.headers, json={"value": None})).json()
    assert c["values"]["studies_included"] == 1 and c["adjusted"] == {}
    bad = await client.put(
        f"{p['base']}/prisma/adjustments/anything", headers=ana.headers, json=body
    )
    assert bad.status_code == 422


async def test_flow_diagram_comes_from_r_in_both_languages_and_as_docx(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, _, _, p = await _flow(client, make_user, session)
    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    # The SVG device writes text as glyph outlines, so the language is checked on the
    # texts sent to R (test below); here the figure itself must come back from R.
    for lang in ("pt-BR", "en"):
        r = await client.post(
            f"{p['base']}/prisma/flow", headers=reader.headers, json={"format": "svg", "lang": lang}
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content
        assert "prisma" in r.headers["content-disposition"]
    png = await client.post(f"{p['base']}/prisma/flow", headers=ana.headers, json={"format": "png"})
    assert png.content[1:4] == b"PNG"
    docx = await client.get(
        f"{p['base']}/prisma/flow.docx", headers=ana.headers, params={"lang": "en"}
    )
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert "prisma-flow-diagram" in docx.headers["content-disposition"]


async def test_box_texts_in_the_output_language(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    from app.modules.prisma.service import PrismaCounts, boxes

    ana, _, _, p = await _flow(client, make_user, session)
    c = PrismaCounts.model_validate(
        (await client.get(f"{p['base']}/prisma/counts", headers=ana.headers)).json()
    )
    pt, en = boxes(c, "pt-BR"), boxes(c, "en")
    assert pt["screened"] == "Registros triados" + NL + "(n = 6)"
    assert en["screened"] == "Records screened" + NL + "(n = 6)"
    assert "População errada (n = 1)" in pt["assessed_excluded"]
    assert "Wrong population (n = 1)" in en["assessed_excluded"]
    assert "PubMed (n = 6)" in en["identified"] and "Total (n = 7)" in en["identified"]
