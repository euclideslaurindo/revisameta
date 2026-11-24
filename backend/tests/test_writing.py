"""Abstract support and Methods/Results draft without AI (stage 8 steps 5 and 6).
Public dat.bcg data through the real R service; checklist items are our own summaries."""

import io

from docx import Document
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.tutor import facts_of
from app.modules.prisma.abstract_items import CODES
from tests.test_analysis_subgroups import _bcg
from tests.test_consensus import MakeUser, _join


def test_prisma_for_abstracts_has_twelve_items() -> None:
    assert [f"A{i}" for i in range(1, 13)] == CODES


async def test_abstracts_checklist_is_separate_from_prisma_2020(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, _ = await _bcg(client, make_user, session)
    url = f"{p['base']}/prisma/checklist"
    out = (await client.get(url, headers=ana.headers, params={"kind": "abstracts"})).json()
    assert len(out["rows"]) == 12 and "abstracts" in out["source"]
    r = await client.put(
        f"{url}/A4", headers=ana.headers, json={"status": "reported", "location": "Métodos"}
    )
    assert r.status_code == 200 and r.json()["code"] == "A4"
    full = (await client.get(url, headers=ana.headers)).json()
    assert len(full["rows"]) == 42 and full["reported"] == 0
    docx = await client.get(f"{url}.docx", headers=ana.headers, params={"kind": "abstracts"})
    assert "prisma-abstracts-checklist" in docx.headers["content-disposition"]


async def test_abstract_draft_uses_the_numbers_of_the_system(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    analysis = {
        "outcome_id": outcome,
        "timepoint": "5 anos",
        "measure": "RR",
        "method": "REML",
        "test": "z",
    }
    run = (
        await client.post(f"{p['base']}/analyses/run", headers=ana.headers, json=analysis)
    ).json()
    facts = facts_of(run["result"], "RR", "pt-BR")
    r = await client.post(
        f"{p['base']}/writing/abstract/draft", headers=ana.headers, json={"analysis": analysis}
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert facts["pooled_effect"] in s["results"] and facts["i2"] in s["results"]
    assert s["conclusion"] == "[conclusão do grupo]"
    assert "[descreva as bases" in s["methods"]  # no search imported: left to the group

    docx = await client.post(
        f"{p['base']}/writing/methods-results.docx",
        headers=ana.headers,
        json={"lang": "en", "analysis": analysis},
    )
    text = "\n".join(x.text for x in Document(io.BytesIO(docx.content)).paragraphs)
    assert "Methods" in text and facts_of(run["result"], "RR", "en")["pooled_effect"] in text


async def test_saving_the_abstract_with_limits_and_roles(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, _ = await _bcg(client, make_user, session)
    url = f"{p['base']}/writing/abstract"
    assert (await client.get(url, headers=ana.headers)).json()["version"] is None
    body = {"text": "Objetivo: x.", "word_limit": 300, "char_limit": 2500}
    out = (await client.put(url, headers=ana.headers, json=body)).json()
    assert out["word_limit"] == 300 and out["version"] == 1
    assert (await client.put(url, headers=ana.headers, json=body)).status_code == 409
    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    assert (
        await client.put(url, headers=reader.headers, json={**body, "version": 1})
    ).status_code == 403
