from httpx import AsyncClient

from app.integrations.email import InMemoryEmailSender
from tests.conftest import PASSWORD, token_from_link

NEW = "nova-senha-forte-123"


async def _login(client: AsyncClient, email: str, password: str) -> int:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.status_code


async def test_forgot_password_resets_and_signs_out(
    client: AsyncClient, make_user, outbox: InMemoryEmailSender
) -> None:
    ana = await make_user("Ana")
    old_cookie = client.cookies.get("rm_refresh")
    r = await client.post("/api/v1/auth/forgot-password", json={"email": ana.email.upper()})
    assert r.status_code == 204
    mail = outbox.outbox[-1]
    assert "redefinir-senha" in mail.body
    token = token_from_link(mail.body)

    r = await client.post("/api/v1/auth/reset-password", json={"token": token, "password": "fraca"})
    assert r.json()["code"] == "auth.weak_password"
    r = await client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW})
    assert r.status_code == 204
    # Single use.
    r = await client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW})
    assert r.json()["code"] == "auth.invalid_token"

    assert await _login(client, ana.email, PASSWORD) == 401
    # The old session was signed out.
    client.cookies.set("rm_refresh", old_cookie or "", path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert await _login(client, ana.email, NEW) == 200


async def test_forgot_password_does_not_reveal_accounts(
    client: AsyncClient, outbox: InMemoryEmailSender
) -> None:
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "ninguem@example.org"})
    assert r.status_code == 204
    assert outbox.outbox == []


async def test_new_reset_link_cancels_the_old_one(
    client: AsyncClient, make_user, outbox: InMemoryEmailSender
) -> None:
    ana = await make_user("Ana")
    await client.post("/api/v1/auth/forgot-password", json={"email": ana.email})
    first = token_from_link(outbox.outbox[-1].body)
    await client.post("/api/v1/auth/forgot-password", json={"email": ana.email})
    r = await client.post("/api/v1/auth/reset-password", json={"token": first, "password": NEW})
    assert r.json()["code"] == "auth.invalid_token"


async def test_change_password_needs_current_one(client: AsyncClient, make_user) -> None:
    ana = await make_user("Ana")
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "errada-123456", "new_password": NEW},
        headers=ana.headers,
    )
    assert r.json()["code"] == "auth.wrong_password"
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW},
        headers=ana.headers,
    )
    assert r.status_code == 204
    # This device stays signed in.
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    assert await _login(client, ana.email, NEW) == 200


async def test_change_password_requires_login(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW},
    )
    assert r.status_code == 401
