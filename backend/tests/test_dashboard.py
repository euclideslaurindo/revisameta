"""Project dashboard: stage progress, pending per person and deadline countdown."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.test_extraction import MakeUser, _join, _project, _start


async def test_dashboard_counts_stages_and_pending_per_person(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, out = await make_user("Ana"), await make_user("Bia"), await make_user("Fora")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["extractor"])
    project = (await client.get(p["base"], headers=ana.headers)).json()
    deadline = (datetime.now(UTC).date() + timedelta(days=10)).isoformat()
    await client.patch(
        p["base"], json={"version": project["version"], "deadline": deadline}, headers=ana.headers
    )
    await _start(client, bia, p)

    r = await client.get(f"{p['base']}/dashboard", headers=bia.headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["days_left"] == 10 and d["studies"] == 1
    stages = {s["key"]: s for s in d["stages"]}
    # One outcome and one group: the protocol still needs a second group to compare.
    assert stages["protocol"]["done"] == 1 and stages["protocol"]["state"] == "in_progress"
    assert stages["extraction"] == {
        "key": "extraction",
        "done": 0,
        "total": 1,
        "state": "not_started",
        "route": "estudos",
    }
    assert "screening" not in stages  # no references imported: no screening stage
    assert d["next_stage"] == "protocol"
    people = {x["name"]: x for x in d["people"]}
    assert people["Bia"]["extractions_open"] == 1 and people["Ana"]["extractions_open"] == 0

    # Isolation: someone outside the project sees nothing.
    r = await client.get(f"{p['base']}/dashboard", headers=out.headers)
    assert r.status_code in (403, 404)
