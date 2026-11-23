"""In-app notifications (stage 6 step 4)."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.test_consensus import MakeUser, _join, _project
from tests.test_screening import _decide, _queue, _team

URL = "/api/v1/notifications"


async def test_mentions_notify_only_new_people_and_never_the_author(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    bia, caio = await make_user("Bia"), await make_user("Caio")
    await _join(client, ana, bia, p["pid"], ["reader"])
    await _join(client, ana, caio, p["pid"], ["reviewer"])
    body = {
        "entity": "study",
        "entity_id": p["study"],
        "text": "Olhem isto",
        "mentions": [bia.id, ana.id],
    }
    c = (await client.post(f"{p['base']}/comments", headers=ana.headers, json=body)).json()
    assert (await client.get(URL, headers=ana.headers)).json()["unread"] == 0
    out = (await client.get(URL, headers=bia.headers)).json()
    assert out["unread"] == 1
    n = out["items"][0]
    assert n["kind"] == "mention" and n["payload"]["author_name"] == "Ana"
    assert n["payload"]["entity_id"] == p["study"] and n["project_title"] == "P"
    # Editing to add Caio notifies Caio only; Bia is not notified twice.
    edit = {"text": "Olhem isto", "mentions": [bia.id, caio.id], "version": c["version"]}
    await client.put(f"{p['base']}/comments/{c['id']}", headers=ana.headers, json=edit)
    assert (await client.get(URL, headers=bia.headers)).json()["unread"] == 1
    assert (await client.get(URL, headers=caio.headers)).json()["unread"] == 1
    # Read one, then all; nobody can read someone else's.
    assert (await client.post(f"{URL}/{n['id']}/read", headers=caio.headers)).status_code == 404
    assert (await client.post(f"{URL}/{n['id']}/read", headers=bia.headers)).status_code == 204
    out = (await client.get(URL, headers=bia.headers)).json()
    assert out["unread"] == 0 and out["items"][0]["read"] is True
    assert (await client.post(f"{URL}/read-all", headers=caio.headers)).status_code == 204
    assert (await client.get(URL, headers=caio.headers)).json()["unread"] == 0


async def test_screening_conflict_notifies_admins_once(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    refs = [i["reference"]["id"] for i in (await _queue(client, bia, p))["items"]]
    await _decide(client, bia, p, refs[0], "include")
    assert (await client.get(URL, headers=ana.headers)).json()["unread"] == 0
    await _decide(client, caio, p, refs[0], "exclude")
    await _decide(client, caio, p, refs[0], "maybe")  # still a conflict: no second notice
    out = (await client.get(URL, headers=ana.headers)).json()
    assert out["unread"] == 1 and out["items"][0]["kind"] == "screening_conflict"
    assert out["items"][0]["payload"]["reference_id"] == refs[0]
    assert (await client.get(URL, headers=bia.headers)).json()["unread"] == 0


async def test_deadline_within_a_week_and_leaving_the_project_hides_it(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    project = (await client.get(p["base"], headers=ana.headers)).json()
    soon = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    r = await client.patch(
        p["base"], headers=ana.headers, json={"deadline": soon, "version": project["version"]}
    )
    assert r.status_code == 200, r.text
    for _ in range(2):
        out = (await client.get(URL, headers=ana.headers)).json()
    assert out["unread"] == 1
    assert out["items"][0]["kind"] == "deadline" and out["items"][0]["payload"]["days"] == 3
