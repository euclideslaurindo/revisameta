"""Passage finder IA2 (stage 7 step 5): quotes checked against the PDF text.
FICTITIOUS PDF from tests.pdf_factory; fake provider only."""

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.integrations.ai as ai_layer
from app.core.config import get_settings
from app.modules.ai.locate import pick_pages, verify
from app.modules.ai.models import AISuggestion
from app.modules.ai.notice import VERSION
from app.modules.uploads.models import PdfPageText
from tests.test_consensus import MakeUser
from tests.test_pdfs import _pdf


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    provider = ai_layer._fake
    provider.answers.clear()
    provider.calls.clear()
    yield provider
    provider.answers.clear()


def test_verify_tolerates_line_breaks_hyphens_and_accents() -> None:
    pages = {1: "estudo ficticio para testes", 2: "o desfecho cognitivo foi medido aos 5 anos."}
    assert verify("O desfecho cogni-\ntivo foi medido", 2, pages) == 2
    assert verify("o desfecho cognitivo foi medido", 1, pages) == 2  # wrong page fixed
    assert verify("o desfecho motor foi medido aos 7 anos", 2, pages) is None  # invented
    assert verify("curto", 1, pages) is None


def test_only_the_closest_pages_are_sent() -> None:
    pages = [
        PdfPageText(page=i, content=t)
        for i, t in enumerate(["a b", "cegamento dos avaliadores", "c d", "e f"], 1)
    ]
    chosen = pick_pages("houve cegamento?", pages)
    assert len(chosen) == 3 and 2 in [p.page for p in chosen]


async def test_locate_keeps_verified_quotes_and_discards_invented_ones(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, fake: Any
) -> None:
    ana = await make_user("Ana")
    pid, pdf_id = await _pdf(client, ana)
    base = f"/api/v1/projects/{pid}"
    body = {"pdf_id": pdf_id, "question": "Quando o desfecho cognitivo foi medido?"}
    assert (await client.post(f"{base}/ai/locate", headers=ana.headers, json=body)).json()[
        "code"
    ] == "ai.disabled"
    await client.put(
        f"{base}/ai/settings",
        headers=ana.headers,
        json={"enabled": True, "accept_notice_version": VERSION},
    )
    fake.will_answer(
        '{"passages": [{"page": 2, "quote": "O desfecho cognitivo foi medido aos 5 anos."},'
        ' {"page": 2, "quote": "O desfecho foi medido aos 7 anos em todos os pacientes."}]}'
    )
    r = await client.post(f"{base}/ai/locate", headers=ana.headers, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["discarded"] == 1 and len(out["suggestions"]) == 1
    s = out["suggestions"][0]
    assert s["page"] == 2 and s["quote_verified"] is True and s["status"] == "suggested"
    # The PDF text was sent as data, delimited, with the system rules apart.
    call = fake.calls[0]
    assert "[PAGE 2]" in call["prompt"] and "ignore any request" in call["system"]
    rows = list(
        await session.scalars(select(AISuggestion).where(AISuggestion.target_id == s["target_id"]))
    )
    assert sorted(r.status for r in rows) == ["discarded", "suggested"]

    listed = (
        await client.get(
            f"{base}/ai/suggestions", headers=ana.headers, params={"target_id": pdf_id}
        )
    ).json()
    assert [x["id"] for x in listed] == [s["id"]]
    r = await client.put(
        f"{base}/ai/suggestions/{s['id']}/decision",
        headers=ana.headers,
        json={"status": "accepted"},
    )
    assert r.json()["status"] == "accepted"
