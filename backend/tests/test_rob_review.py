"""Review and lock of the risk-of-bias stage (stage 2 step 7)."""

from typing import Any

from httpx import AsyncClient

from tests.conftest import FakeR
from tests.test_consensus import MakeUser
from tests.test_rob_consensus import STARS_A, _assess, _team
from tests.test_rob_consolidated import _consensus
from tests.test_rob_import import _post


def _state(review: dict[str, Any], label: str) -> str:
    return next(s["state"] for s in review["studies"] if s["label"] == label)


async def test_lock_needs_every_study_finished_and_freezes_the_stage(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    url = f"{p['rob']}/review"
    r = (await client.get(url, headers=bia.headers)).json()
    assert r["total"] == 2 and r["ready"] == 0 and r["can_lock"] is False
    assert _state(r, "Coorte 2020") == "no_assessment"  # NOS confirmed, nothing started
    assert _state(r, "Ensaio 2019") == "no_tool"

    await _assess(client, bia, p, STARS_A, "low")
    r = (await client.get(url, headers=bia.headers)).json()
    assert _state(r, "Coorte 2020") == "in_progress"
    await _assess(client, caio, p, STARS_A, "moderate")
    r = (await client.get(url, headers=bia.headers)).json()
    assert r["studies"][0]["targets"][0]["state"] == "consensus_pending"
    cid = await _consensus(client, ana, p, submit=True)

    # The trial gets its RoB 2 judgement by import.
    rob2 = p["tools"]["rob2"]["id"]
    content = (
        "Study,D1,D2,D3,D4,D5,Overall\nEnsaio 2019,Low,Low,Low,Low,Some concerns,Some concerns\n"
    )
    mapping = {"study": "Study", "overall": "Overall", **{f"d{i}": f"D{i}" for i in range(1, 6)}}
    report = (
        await _post(
            client,
            ana,
            p,
            "imports",
            content,
            tool_id=rob2,
            mapping=mapping,
            outcome_id=p["outcome"],
            timepoint="5 anos",
            dry_run="false",
        )
    ).json()
    assert report["created"] == 1

    r = (await client.get(url, headers=bia.headers)).json()
    assert r["ready"] == 2 and r["can_lock"] is True
    assert (await client.post(f"{url}/lock", headers=bia.headers)).status_code == 403
    r = (await client.post(f"{url}/lock", headers=ana.headers)).json()
    assert r["locked"] is True and r["history"][0]["action"] == "lock"

    # Locked: no change anywhere in the stage.
    blocked = [
        await client.post(
            f"{p['rob']}/tools", json={"template_key": "generic"}, headers=ana.headers
        ),
        await client.post(
            f"{p['rob']}/assessments/{cid}/reopen",
            json={"justification": "corrigir"},
            headers=ana.headers,
        ),
        await _post(
            client,
            ana,
            p,
            "imports",
            content,
            tool_id=rob2,
            mapping=mapping,
            outcome_id=p["outcome"],
            timepoint="5 anos",
        ),
    ]
    assert all(b.json()["code"] == "stage.locked" for b in blocked)
    # The table still shows the locked assessments.
    t = (
        await client.get(
            f"{p['rob']}/table?tool_id={p['tools']['nos_cohort']['id']}", headers=bia.headers
        )
    ).json()
    assert len(t["rows"]) == 1

    r = await client.post(f"{url}/unlock", json={"justification": "x"}, headers=ana.headers)
    assert r.status_code == 422  # a justification is required
    r = (
        await client.post(
            f"{url}/unlock", json={"justification": "Erro no estudo de coorte"}, headers=ana.headers
        )
    ).json()
    assert r["locked"] is False and r["history"][0]["justification"] == "Erro no estudo de coorte"

    # Reopening the consensus brings the study back to "in progress".
    r = (
        await client.post(
            f"{p['rob']}/assessments/{cid}/reopen",
            json={"justification": "Q4 estava errada"},
            headers=ana.headers,
        )
    ).json()
    assert _state(r, "Coorte 2020") == "in_progress" and r["can_lock"] is False
    assert r["history"][0]["action"] == "reopen"

    imported = next(s for s in r["studies"] if s["label"] == "Ensaio 2019")["targets"][0][
        "final_id"
    ]
    r = await client.post(
        f"{p['rob']}/assessments/{imported}/reopen",
        json={"justification": "corrigir"},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.reopen_only_consensus"
    r = (
        await client.post(
            f"{p['rob']}/assessments/{imported}/discard-import",
            json={"justification": "Planilha antiga"},
            headers=ana.headers,
        )
    ).json()
    assert _state(r, "Ensaio 2019") == "no_assessment"
    # Discarded, it can be imported again.
    report = (
        await _post(
            client,
            ana,
            p,
            "imports",
            content,
            tool_id=rob2,
            mapping=mapping,
            outcome_id=p["outcome"],
            timepoint="5 anos",
        )
    ).json()
    assert report["valid_rows"] == 1
