from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, is_strong_password, verify_password
from app.integrations.captcha import CaptchaVerifier, get_captcha_verifier
from app.integrations.email import InMemoryEmailSender
from app.main import app
from app.modules.auth.models import RefreshToken, User
from tests.conftest import PASSWORD, LoggedUser, token_from_link

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]
REGISTER = "/api/v1/auth/register"


def _register_body(email: str = "ana@example.org", **extra: Any) -> dict[str, Any]:
    return {"name": "Ana", "email": email, "password": PASSWORD, "accept_terms": True, **extra}


def test_password_hashing_uses_argon2id() -> None:
    hashed = hash_password("abc123def456")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "abc123def456")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")


def test_password_policy() -> None:
    assert is_strong_password("senhaforte1")
    assert not is_strong_password("curta1")
    assert not is_strong_password("somenteletras")
    assert not is_strong_password("1234567890")


async def test_register_sends_verification_email_in_user_language(
    client: AsyncClient, outbox: InMemoryEmailSender
) -> None:
    r = await client.post(REGISTER, json=_register_body(), headers={"Accept-Language": "en"})
    assert r.status_code == 201
    assert r.json()["email_verified_at"] is None
    assert r.json()["ui_language"] == "en"
    assert outbox.outbox[0].to == "ana@example.org"
    assert outbox.outbox[0].subject == "Confirm your e-mail on RevisaMeta"
    assert "/verificar-email?token=" in outbox.outbox[0].body


async def test_register_requires_terms_and_strong_password(client: AsyncClient) -> None:
    r = await client.post(REGISTER, json=_register_body(accept_terms=False))
    assert r.json()["code"] == "auth.terms_required"
    r = await client.post(REGISTER, json=_register_body(password="fraca"))
    assert r.json()["code"] == "auth.weak_password"


async def test_register_rejects_duplicate_email_case_insensitive(client: AsyncClient) -> None:
    await client.post(REGISTER, json=_register_body("ana@example.org"))
    r = await client.post(REGISTER, json=_register_body("ANA@Example.org"))
    assert r.status_code == 409
    assert r.json()["code"] == "auth.email_taken"


async def test_terms_version_is_recorded(client: AsyncClient, session: AsyncSession) -> None:
    await client.post(REGISTER, json=_register_body())
    user = (await session.scalars(select(User))).one()
    assert user.terms_version is not None
    assert user.terms_accepted_at is not None


async def test_cannot_login_before_verifying_email(
    client: AsyncClient, outbox: InMemoryEmailSender
) -> None:
    await client.post(REGISTER, json=_register_body())
    r = await client.post(
        "/api/v1/auth/login", json={"email": "ana@example.org", "password": PASSWORD}
    )
    assert r.status_code == 403
    assert r.json()["code"] == "auth.email_not_verified"

    token = token_from_link(outbox.outbox[0].body)
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 204
    r = await client.post(
        "/api/v1/auth/login", json={"email": "ana@example.org", "password": PASSWORD}
    )
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


async def test_verification_token_is_single_use(
    client: AsyncClient, outbox: InMemoryEmailSender
) -> None:
    await client.post(REGISTER, json=_register_body())
    token = token_from_link(outbox.outbox[0].body)
    await client.post("/api/v1/auth/verify-email", json={"token": token})
    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 400
    assert r.json()["code"] == "auth.invalid_token"


async def test_resend_verification_does_not_reveal_accounts(
    client: AsyncClient, outbox: InMemoryEmailSender
) -> None:
    await client.post(REGISTER, json=_register_body())
    r1 = await client.post("/api/v1/auth/resend-verification", json={"email": "ana@example.org"})
    r2 = await client.post("/api/v1/auth/resend-verification", json={"email": "nobody@example.org"})
    assert r1.status_code == r2.status_code == 204
    assert len(outbox.outbox) == 2


async def test_wrong_password_is_generic(client: AsyncClient, make_user: MakeUser) -> None:
    user = await make_user()
    r = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "errada123x"}
    )
    assert r.status_code == 401
    assert r.json()["code"] == "auth.invalid_credentials"
    r = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.org", "password": "errada123x"}
    )
    assert r.json()["code"] == "auth.invalid_credentials"


async def test_me_requires_a_valid_token(client: AsyncClient, make_user: MakeUser) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    user = await make_user(name="Bia")
    r = await client.get("/api/v1/auth/me", headers=user.headers)
    assert r.json()["name"] == "Bia"


async def test_update_profile_language(client: AsyncClient, make_user: MakeUser) -> None:
    user = await make_user()
    r = await client.patch("/api/v1/auth/me", json={"ui_language": "en"}, headers=user.headers)
    assert r.json()["ui_language"] == "en"


async def test_refresh_cookie_is_httponly_and_rotates(
    client: AsyncClient, make_user: MakeUser
) -> None:
    await make_user()
    cookie_header = client.cookies.get("rm_refresh")
    assert cookie_header

    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=strict" in r.headers["set-cookie"].lower()
    assert client.cookies.get("rm_refresh") != cookie_header


async def test_reusing_an_old_refresh_token_revokes_the_session(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    await make_user()
    old = client.cookies.get("rm_refresh")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    newest = client.cookies.get("rm_refresh")

    client.cookies.set("rm_refresh", old, path="/api/v1/auth")
    stolen = await client.post("/api/v1/auth/refresh")
    assert stolen.status_code == 401

    client.cookies.set("rm_refresh", newest, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    tokens = (await session.scalars(select(RefreshToken))).all()
    assert all(t.revoked_at is not None for t in tokens)


async def test_logout_revokes_refresh(client: AsyncClient, make_user: MakeUser) -> None:
    await make_user()
    token = client.cookies.get("rm_refresh")
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set("rm_refresh", token, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == "auth.session_expired"


@pytest.fixture
def captcha_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "turnstile_enabled", True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": b"response=good" in request.content})

    verifier = CaptchaVerifier(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_captcha_verifier] = lambda: verifier
    yield
    app.dependency_overrides.pop(get_captcha_verifier, None)


async def test_register_requires_captcha_when_enabled(
    client: AsyncClient, captcha_on: None
) -> None:
    r = await client.post(REGISTER, json=_register_body(captcha_token="bad"))
    assert r.json()["code"] == "auth.captcha_failed"
    r = await client.post(REGISTER, json=_register_body(captcha_token="good"))
    assert r.status_code == 201


async def test_captcha_required_after_repeated_login_failures(
    client: AsyncClient, make_user: MakeUser, captcha_on: None
) -> None:
    user = await make_user()
    for _ in range(3):
        await client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "errada123x"}
        )
    r = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.json()["code"] == "auth.captcha_failed"
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD, "captcha_token": "good"},
    )
    assert r.status_code == 200


async def test_login_is_rate_limited(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "login_rate_limit", "3/minute")
    body = {"email": "x@example.org", "password": "errada123x"}
    codes = [(await client.post("/api/v1/auth/login", json=body)).status_code for _ in range(4)]
    assert codes[-1] == 429
