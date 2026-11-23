"""Comments with mentions (stage 6 step 3)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.test_consensus import MakeUser, _join, _project


async def test_comment_mention_edit_and_remove(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    bia = await make_user("Bia")
    await _join(client, ana, bia, p["pid"], ["reader"])
    outsider = await make_user("Caio")
    url = f"{p['base']}/comments"

    members = (await client.get(f"{url}/members", headers=bia.headers)).json()
    assert {m["name"] for m in members} == {"Ana", "Bia"}
    assert all("email" not in m for m in members)
    bia_id = next(m["user_id"] for m in members if m["name"] == "Bia")

    body = {
        "entity": "study",
        "entity_id": p["study"],
        "field": "group1.sd",
        "text": "  @Bia confere se é DP ou EP?  ",
        "mentions": [bia_id, bia_id],
    }
    r = await client.post(url, headers=ana.headers, json=body)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["text"] == "@Bia confere se é DP ou EP?" and c["field"] == "group1.sd"
    assert [m["name"] for m in c["mentions"]] == ["Bia"] and c["author_name"] == "Ana"

    # Readers comment too; outsiders cannot be mentioned.
    reply = {**body, "text": "É EP, tabela 2.", "mentions": [], "field": None}
    assert (await client.post(url, headers=bia.headers, json=reply)).status_code == 201
    outsider_id = outsider.id
    bad = await client.post(url, headers=ana.headers, json={**body, "mentions": [outsider_id]})
    assert bad.status_code == 422 and bad.json()["code"] == "comments.mention_not_member"
    # The target must belong to the project.
    other = await client.post(
        url, headers=ana.headers, json={**body, "entity_id": str(uuid.uuid4())}
    )
    assert other.status_code == 404

    params = {"entity": "study", "entity_id": p["study"]}
    listed = (await client.get(url, headers=bia.headers, params=params)).json()
    assert [x["text"] for x in listed] == ["@Bia confere se é DP ou EP?", "É EP, tabela 2."]

    # Only the author edits; stale versions conflict.
    edit = {"text": "Confere o DP, por favor.", "mentions": [bia_id], "version": c["version"]}
    assert (await client.put(f"{url}/{c['id']}", headers=bia.headers, json=edit)).status_code == 403
    r = await client.put(f"{url}/{c['id']}", headers=ana.headers, json=edit)
    assert r.status_code == 200 and r.json()["edited"] is True
    assert (await client.put(f"{url}/{c['id']}", headers=ana.headers, json=edit)).status_code == 409
    audit = await session.scalars(select(AuditLog).where(AuditLog.entity == "comments"))
    assert audit.first() is not None

    # The author or an admin removes (soft delete); others cannot.
    reply_id = listed[1]["id"]
    assert (await client.delete(f"{url}/{c['id']}", headers=bia.headers)).status_code == 403
    assert (await client.delete(f"{url}/{reply_id}", headers=ana.headers)).status_code == 204
    left = (await client.get(url, headers=ana.headers, params=params)).json()
    assert [x["id"] for x in left] == [c["id"]]
