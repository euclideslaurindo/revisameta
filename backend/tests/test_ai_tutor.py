"""Tutor IA1 (stage 7 step 4): numbers only from R, anything else flagged. Fake provider;
real R service with the public dat.bcg data."""

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.integrations.ai as ai_layer
from app.core.config import get_settings
from app.modules.ai.notice import VERSION
from app.modules.ai.tutor import facts_of, fill
from tests.test_analysis_subgroups import _bcg
from tests.test_consensus import MakeUser


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    provider = ai_layer._fake
    provider.answers.clear()
    provider.calls.clear()
    yield provider
    provider.answers.clear()


async def _on(client: AsyncClient, user: Any, p: dict[str, Any]) -> None:
    r = await client.put(
        f"{p['base']}/ai/settings",
        headers=user.headers,
        json={"enabled": True, "accept_notice_version": VERSION},
    )
    assert r.status_code == 200, r.text


def test_fill_replaces_placeholders_and_flags_invented_numbers() -> None:
    facts = {"pooled_effect": "0,49", "i2": "92,1%", "ci_level": "95"}
    text, unverified, used = fill(
        "O efeito foi {{pooled_effect}} (IC {{ci_level}}%), I² {{i2}}; cerca de 30% e {{tau}}.",
        facts,
    )
    assert text.startswith("O efeito foi 0,49 (IC 95%), I² 92,1%")
    assert unverified == ["30", "{{tau}}"]
    assert used == ["pooled_effect", "ci_level", "i2"]


async def test_tutor_explains_an_analysis_with_numbers_from_r(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, fake: Any
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    url = f"{p['base']}/ai/tutor"
    analysis = {
        "outcome_id": outcome,
        "timepoint": "5 anos",
        "measure": "RR",
        "method": "REML",
        "test": "z",
    }
    body = {"question": "O que significa meu I²?", "analysis": analysis}
    assert (await client.post(url, headers=ana.headers, json=body)).json()["code"] == "ai.disabled"
    assert fake.calls == []

    await _on(client, ana, p)
    run = (
        await client.post(f"{p['base']}/analyses/run", headers=ana.headers, json=analysis)
    ).json()
    expected = facts_of(run["result"], "RR", "pt-BR")
    fake.will_answer('{"text": "O RR combinado foi {{pooled_effect}} e o I² foi {{i2}}."}')
    out = (await client.post(url, headers=ana.headers, json=body)).json()
    assert (
        out["text"]
        == f"O RR combinado foi {expected['pooled_effect']} e o I² foi {expected['i2']}."
    )
    assert out["unverified"] == [] and out["cached"] is False
    # RR is shown on its own scale (from R's exp values), never the log.
    assert expected["pooled_effect"].startswith("0,")
    sent = fake.calls[0]["prompt"]
    assert "{{pooled_effect}}" in sent and expected["pooled_effect"] not in sent
    assert "@" not in sent  # no e-mails

    # A number written by the AI itself is flagged.
    fake.will_answer('{"text": "O efeito foi de 0,49, ou seja, {{pooled_effect}}."}')
    out = (
        await client.post(url, headers=ana.headers, json={**body, "question": "E o efeito?"})
    ).json()
    assert out["unverified"] == ["0,49"]


async def test_concept_question_without_analysis_and_quota_message(
    client: AsyncClient,
    make_user: MakeUser,
    session: AsyncSession,
    fake: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ana, p, _ = await _bcg(client, make_user, session)
    await _on(client, ana, p)
    fake.will_answer('{"text": "Heterogeneidade é quanto os estudos diferem entre si."}')
    r = await client.post(
        f"{p['base']}/ai/tutor", headers=ana.headers, json={"question": "O que é heterogeneidade?"}
    )
    assert r.status_code == 200 and r.json()["facts_used"] == []
    monkeypatch.setattr(get_settings(), "ai_calls_per_user_day", 1)
    r = await client.post(
        f"{p['base']}/ai/tutor", headers=ana.headers, json={"question": "E o I²?"}
    )
    assert r.status_code == 429 and r.json()["code"] == "ai.quota_exceeded"
