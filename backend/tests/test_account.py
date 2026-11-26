from httpx import AsyncClient

from tests.conftest import PASSWORD
from tests.test_projects import _invite_and_join, _project


async def _delete(client: AsyncClient, user, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return await client.post(
        "/api/v1/auth/me/delete", json={"password": password}, headers=user.headers
    )


async def test_export_has_account_and_projects(client: AsyncClient, make_user) -> None:
    ana = await make_user("Ana")
    await _project(client, ana, "Minha revisão")
    r = await client.get("/api/v1/auth/me/export", headers=ana.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["account"]["email"] == ana.email
    assert [p["title"] for p in body["projects"]] == ["Minha revisão"]


async def test_delete_account_anonymises_and_removes_solo_projects(
    client: AsyncClient, make_user
) -> None:
    ana = await make_user("Ana")
    project = await _project(client, ana, "Só minha")
    assert (await _delete(client, ana, "errada-123456")).json()["code"] == "auth.wrong_password"

    check = (await client.get("/api/v1/auth/me/deletion-check", headers=ana.headers)).json()
    assert check["projects_deleted"] == ["Só minha"]
    assert check["blocking"] == []

    assert (await _delete(client, ana)).status_code == 204
    # Signed out and cannot sign in again.
    assert (await client.get("/api/v1/auth/me", headers=ana.headers)).status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": ana.email, "password": PASSWORD})
    assert r.status_code == 401
    # The e-mail is free for a new account.
    await make_user("Ana de novo", email=ana.email)
    bia = await make_user("Bia")
    r = await client.get(f"/api/v1/projects/{project['id']}", headers=bia.headers)
    assert r.status_code == 404


async def test_owner_of_shared_project_must_hand_over_first(client: AsyncClient, make_user) -> None:
    ana = await make_user("Ana")
    bia = await make_user("Bia")
    project = await _project(client, ana, "Compartilhado")
    await _invite_and_join(client, ana, bia, project["id"], ["admin"])

    check = (await client.get("/api/v1/auth/me/deletion-check", headers=ana.headers)).json()
    assert [b["reason"] for b in check["blocking"]] == ["owner_with_members"]
    assert (await _delete(client, ana)).json()["code"] == "account.transfer_first"

    members = (
        await client.get(f"/api/v1/projects/{project['id']}/members", headers=ana.headers)
    ).json()
    member = next(m for m in members if m["user_id"] == bia.id)
    r = await client.post(
        f"/api/v1/projects/{project['id']}/transfer-ownership",
        json={"member_id": member["id"]},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    assert (await _delete(client, ana)).status_code == 204

    # The project stays with Bia; Ana's membership is gone and her name is anonymised.
    r = await client.get(f"/api/v1/projects/{project['id']}/members", headers=bia.headers)
    names = [m["name"] for m in r.json()]
    assert "Ana" not in names


async def test_plain_member_can_leave_by_deleting(client: AsyncClient, make_user) -> None:
    ana = await make_user("Ana")
    bia = await make_user("Bia")
    project = await _project(client, ana)
    await _invite_and_join(client, ana, bia, project["id"], ["reviewer"])
    check = (await client.get("/api/v1/auth/me/deletion-check", headers=bia.headers)).json()
    assert check == {"blocking": [], "projects_deleted": [], "memberships_left": 1}
    assert (await _delete(client, bia)).status_code == 204
    r = await client.get(f"/api/v1/projects/{project['id']}", headers=ana.headers)
    assert r.status_code == 200
