"""Accuracy metrics, automatic switch-off and AI-use statement (stage 7 step 6)."""

import io
from collections.abc import Iterator
from typing import Any

import pytest
from docx import Document
from httpx import AsyncClient

import app.integrations.ai as ai_layer
from app.core.config import get_settings
from app.modules.ai.notice import VERSION
from tests.test_consensus import MakeUser
from tests.test_pdfs import _pdf

GOOD = '{"page": 2, "quote": "O desfecho cognitivo foi medido aos 5 anos."}'


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    monkeypatch.setattr(get_settings(), "ai_accuracy_min_decided", 4)
    provider = ai_layer._fake
    provider.answers.clear()
    provider.calls.clear()
    yield provider
    provider.answers.clear()


async def test_low_accuracy_switches_the_feature_off_with_a_notice(
    client: AsyncClient, make_user: MakeUser, fake: Any
) -> None:
    ana = await make_user("Ana")
    pid, pdf_id = await _pdf(client, ana)
    base = f"/api/v1/projects/{pid}"
    await client.put(
        f"{base}/ai/settings",
        headers=ana.headers,
        json={"enabled": True, "accept_notice_version": VERSION},
    )
    ids = []
    for i in range(4):
        fake.will_answer('{"passages": [' + GOOD + "]}")
        r = await client.post(
            f"{base}/ai/locate",
            headers=ana.headers,
            json={"pdf_id": pdf_id, "question": f"desfecho cognitivo {i}"},
        )
        ids.append(r.json()["suggestions"][0]["id"])
    # 1 of 4 helped: 25% < 80%. Below the minimum (3 decided) nothing happens yet.
    for sid, status in zip(ids[:3], ["accepted", "rejected", "rejected"], strict=True):
        await client.put(
            f"{base}/ai/suggestions/{sid}/decision", headers=ana.headers, json={"status": status}
        )
    m = (await client.get(f"{base}/ai/metrics", headers=ana.headers)).json()["tasks"]
    locate = next(t for t in m if t["task"] == "locate")
    assert locate["accuracy"] is None and locate["disabled"] is False
    await client.put(
        f"{base}/ai/suggestions/{ids[3]}/decision", headers=ana.headers, json={"status": "rejected"}
    )
    m = (await client.get(f"{base}/ai/metrics", headers=ana.headers)).json()["tasks"]
    locate = next(t for t in m if t["task"] == "locate")
    assert locate["accuracy"] == 0.25 and locate["disabled"] is True
    r = await client.post(
        f"{base}/ai/locate", headers=ana.headers, json={"pdf_id": pdf_id, "question": "outra"}
    )
    assert r.json()["code"] == "ai.low_accuracy"
    notices = (await client.get("/api/v1/notifications", headers=ana.headers)).json()["items"]
    assert any(n["kind"] == "ai_disabled" and n["payload"]["accuracy"] == 25 for n in notices)

    # The statement for the manuscript reports what was used and the hit rate.
    r = await client.get(f"{base}/ai/statement.docx", headers=ana.headers, params={"lang": "en"})
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "locate-v1" in text and "Accuracy: 25%" in text and "fake-1" in text

    # An admin turns it back on by hand.
    s = (await client.get(f"{base}/ai/settings", headers=ana.headers)).json()
    r = await client.put(
        f"{base}/ai/settings",
        headers=ana.headers,
        json={"enabled": True, "functions": ["tutor", "locate"], "version": s["version"]},
    )
    assert r.json()["disabled_functions"] == {}


async def test_statement_without_any_use(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user("Ana")
    pid, _ = await _pdf(client, ana)
    r = await client.get(f"/api/v1/projects/{pid}/ai/statement.docx", headers=ana.headers)
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "Nenhuma função de IA foi usada" in text
