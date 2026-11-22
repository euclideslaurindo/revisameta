"""Screening prioritization (stage 5 step 5): TF-IDF + logistic regression only changes
the order of the list. Every record is FICTITIOUS.
"""

import uuid
from typing import Any

from httpx import AsyncClient

from app.modules.screening.priority import rank
from tests.test_consensus import MakeUser, _join, _project
from tests.test_search_import import _import

ON = "FICTITIOUS craniosynostosis surgery and cognitive outcome in children, record"
OFF = "FICTITIOUS rat model of bone healing in the laboratory, record"


def test_rank_puts_the_likely_inclusions_first() -> None:
    ids = [uuid.uuid4() for _ in range(14)]
    texts = {i: (ON if n % 2 == 0 else OFF) + f" {n}" for n, i in enumerate(ids)}
    labels = {i: (1 if n % 2 == 0 else 0) for n, i in enumerate(ids[:10])}
    scores = rank(texts, labels)
    new_on, new_off = ids[10], ids[11]
    assert scores[new_on] > 0.5 > scores[new_off]


def _ris(n: int) -> bytes:
    out = []
    for i in range(n):
        title = (ON if i % 2 == 0 else OFF) + f" {i}"
        out.append(f"TY  - JOUR\nTI  - {title}\nPY  - 2020\nER  - \n")
    return "".join(out).encode()


async def test_priority_needs_decisions_then_orders_without_removing(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    await _import(client, ana, p, "busca.ris", _ris(24))
    base = f"{p['base']}/screening"
    queue = (await client.get(f"{base}/queue", headers=ana.headers, params={"limit": 200})).json()
    refs = [(i["reference"]["id"], i["reference"]["title"]) for i in queue["items"]]

    # Too few decisions: the job fails with a clear reason, nothing changes.
    job = (await client.post(f"{base}/priority", headers=ana.headers)).json()
    state = (await client.get(f"{p['base']}/jobs/{job['job_id']}", headers=ana.headers)).json()
    assert state["status"] == "failed"
    assert state["error_code"] == "screening.priority_needs_decisions"

    for ref_id, title in refs[:12]:
        decision = "include" if title.startswith(ON) else "exclude"
        await client.post(
            f"{base}/references/{ref_id}/decision",
            headers=ana.headers,
            json={"decision": decision},
        )
    job = (await client.post(f"{base}/priority", headers=ana.headers)).json()
    state = (await client.get(f"{p['base']}/jobs/{job['job_id']}", headers=ana.headers)).json()
    assert state["status"] == "succeeded", state
    info = (await client.get(f"{base}/priority", headers=ana.headers)).json()
    assert info["includes"] == 6 and info["excludes"] == 6 and info["scored"] == 24

    todo = (
        await client.get(
            f"{base}/queue", headers=ana.headers, params={"order": "priority", "limit": 6}
        )
    ).json()
    assert todo["total"] == 12 and todo["next_offset"] == 6
    assert all(i["reference"]["title"].startswith(ON) for i in todo["items"])
    rest = (
        await client.get(
            f"{base}/queue",
            headers=ana.headers,
            params={"order": "priority", "limit": 6, "offset": 6},
        )
    ).json()
    assert all(i["reference"]["title"].startswith(OFF) for i in rest["items"])
    assert rest["next_offset"] is None
    # Changing other settings keeps the model info.
    await client.put(f"{base}/settings", headers=ana.headers, json={"blind": True})
    assert (await client.get(f"{base}/priority", headers=ana.headers)).json()["scored"] == 24


async def test_readers_cannot_train(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    p = await _project(client, ana)
    reader: Any = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    r = await client.post(f"{p['base']}/screening/priority", headers=reader.headers)
    assert r.status_code == 403
