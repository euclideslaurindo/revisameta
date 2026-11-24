# ruff: noqa: E501  (scripted JSON answers read better on one line each)
"""IA3 to IA6 (stage 7, second part). Fake provider; FICTITIOUS PDF; public dat.bcg."""

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.integrations.ai as ai_layer
from app.core.config import get_settings
from app.modules.ai.assist import number_in_quote
from app.modules.ai.notice import VERSION
from tests.test_analysis_subgroups import _bcg
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


async def _on(client: AsyncClient, user: Any, base: str) -> None:
    r = await client.put(
        f"{base}/ai/settings",
        headers=user.headers,
        json={"enabled": True, "accept_notice_version": VERSION},
    )
    assert r.status_code == 200, r.text


def test_number_must_be_printed_in_its_quote() -> None:
    assert number_in_quote("5", "medido aos 5 anos")
    assert number_in_quote("92,5", "média 92.5 (DP 10)")
    assert not number_in_quote("93", "média 92.5 (DP 10)")
    assert not number_in_quote("cinco", "aos 5 anos")


async def test_extraction_and_rob_hints_need_real_quotes(
    client: AsyncClient, make_user: MakeUser, fake: Any
) -> None:
    ana = await make_user("Ana")
    pid, pdf_id = await _pdf(client, ana)
    base = f"/api/v1/projects/{pid}"
    await _on(client, ana, base)

    fake.will_answer(
        '{"values": ['
        '{"field": "n", "value": "5", "quote": "O desfecho cognitivo foi medido aos 5 anos.", "page": 2},'
        '{"field": "mean", "value": "7", "quote": "O desfecho cognitivo foi medido aos 5 anos.", "page": 2},'
        '{"field": "sd", "value": "3", "quote": "Desvio-padrao de 3 pontos em cada grupo.", "page": 2}'
        '], "dispersion_warning": "A Tabela 2 diz media e DP."}'
    )
    r = await client.post(
        f"{base}/ai/extract", headers=ana.headers, json={"pdf_id": pdf_id, "request": "idade"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    # "7" is not in its quote and the third quote is not in the PDF: both discarded.
    assert out["discarded"] == 2 and len(out["suggestions"]) == 1
    assert out["dispersion_warning"] == "A Tabela 2 diz media e DP."

    fake.will_answer(
        '{"answer": "Y", "quote": "Tabela 2: media e DP por grupo.", "page": 2, "reason": "Relata."}',
        '{"answer": "Talvez", "quote": "", "page": null, "reason": "?"}',
    )
    body = {
        "pdf_id": pdf_id,
        "question": "Os dados foram relatados por grupo?",
        "options": ["Y", "N", "NI"],
    }
    hint = (await client.post(f"{base}/ai/rob-hint", headers=ana.headers, json=body)).json()
    assert hint["discarded"] is False and hint["suggestion"]["page"] == 2
    hint = (
        await client.post(
            f"{base}/ai/rob-hint", headers=ana.headers, json={**body, "question": "Outra pergunta?"}
        )
    ).json()
    assert hint["discarded"] is True  # answer outside the allowed options


async def test_search_help_and_draft(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, fake: Any
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    base = p["base"]
    await _on(client, ana, base)
    project = (await client.get(base, headers=ana.headers)).json()
    await client.patch(
        base,
        headers=ana.headers,
        json={"question": "BCG previne tuberculose?", "version": project["version"]},
    )
    fake.will_answer(
        '{"concepts": [{"concept": "BCG", "mesh": ["BCG Vaccine"], "decs": [], "free_text": ["bcg"]}],'
        ' "pubmed": "(\\"BCG Vaccine\\"[Mesh] OR bcg[tiab])"}'
    )
    r = await client.post(f"{base}/ai/search-help", headers=ana.headers)
    assert r.status_code == 200, r.text
    assert r.json()["concepts"][0]["mesh"] == ["BCG Vaccine"]
    assert "BCG previne tuberculose?" in fake.calls[-1]["prompt"]

    fake.will_answer(
        '{"methods": "Buscamos nas bases [listar]. Foram {{k}} estudos.",'
        ' "results": "O RR foi {{pooled_effect}} (IC {{ci_level}}% {{ci_lower}} a {{ci_upper}}), cerca de 50%."}'
    )
    analysis = {
        "outcome_id": outcome,
        "timepoint": "5 anos",
        "measure": "RR",
        "method": "REML",
        "test": "z",
    }
    r = await client.post(f"{base}/ai/draft", headers=ana.headers, json={"analysis": analysis})
    assert r.status_code == 200, r.text
    out = r.json()
    assert "{{" not in out["results"] and "Foram 13 estudos" in out["methods"]
    assert out["unverified"] == ["50"]
