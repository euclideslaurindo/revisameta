import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.scripts.make_admin import set_admin
from tests.conftest import PASSWORD, LoggedUser


async def _admin(session: AsyncSession, user: LoggedUser) -> None:
    await session.execute(
        update(User).where(User.id == uuid.UUID(user.id)).values(is_system_admin=True)
    )
    await session.commit()


async def test_only_system_admins_reach_admin_routes(client: AsyncClient, make_user) -> None:
    ana = await make_user("Ana")
    for path in ("/api/v1/admin/overview", "/api/v1/admin/users"):
        assert (await client.get(path, headers=ana.headers)).status_code == 403
    r = await client.patch(
        f"/api/v1/admin/users/{ana.id}", json={"is_active": False}, headers=ana.headers
    )
    assert r.status_code == 403


async def test_list_search_and_overview(
    client: AsyncClient, session: AsyncSession, make_user
) -> None:
    admin = await make_user("Admin")
    await make_user("Bruna Souza", email="bruna@example.org")
    await make_user("Carlos")
    await _admin(session, admin)

    page = (await client.get("/api/v1/admin/users", headers=admin.headers)).json()
    assert page["total"] == 3
    page = (await client.get("/api/v1/admin/users?q=SOUZA", headers=admin.headers)).json()
    assert [u["email"] for u in page["items"]] == ["bruna@example.org"]

    overview = (await client.get("/api/v1/admin/overview", headers=admin.headers)).json()
    assert overview["users"] == 3
    assert set(overview["default_quotas"]) == {"projects", "storage_mb", "ai_calls"}


async def test_suspend_signs_out_and_blocks_login(
    client: AsyncClient, session: AsyncSession, make_user
) -> None:
    admin = await make_user("Admin")
    bia = await make_user("Bia")
    await _admin(session, admin)
    r = await client.patch(
        f"/api/v1/admin/users/{bia.id}", json={"is_active": False}, headers=admin.headers
    )
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await client.get("/api/v1/auth/me", headers=bia.headers)).status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": bia.email, "password": PASSWORD})
    assert r.json()["code"] == "auth.account_disabled"

    r = await client.patch(
        f"/api/v1/admin/users/{bia.id}", json={"is_active": True}, headers=admin.headers
    )
    assert r.json()["is_active"] is True


async def test_admin_cannot_lock_out_self(
    client: AsyncClient, session: AsyncSession, make_user
) -> None:
    admin = await make_user("Admin")
    await _admin(session, admin)
    for body in ({"is_active": False}, {"is_system_admin": False}):
        r = await client.patch(f"/api/v1/admin/users/{admin.id}", json=body, headers=admin.headers)
        assert r.json()["code"] == "admin.not_on_self"


async def test_make_admin_script(session: AsyncSession, make_user) -> None:
    ana = await make_user("Ana")
    assert await set_admin(ana.email.upper(), True) == "Ana"
    user = await session.get(User, uuid.UUID(ana.id))
    assert user is not None
    await session.refresh(user)
    assert user.is_system_admin is True
