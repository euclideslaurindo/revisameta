"""Optional 2FA with an authenticator app (stage 8 step 7)."""

import pyotp
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.conftest import PASSWORD
from tests.test_consensus import MakeUser


async def test_setup_enable_login_with_code_and_recovery_and_disable(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user("Ana")
    login = {"email": ana.email, "password": PASSWORD}
    me = (await client.get("/api/v1/auth/me", headers=ana.headers)).json()
    assert me["two_factor"] is False

    setup = (await client.post("/api/v1/auth/2fa/setup", headers=ana.headers)).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/RevisaMeta")
    totp = pyotp.TOTP(setup["secret"])
    # Not on until a valid code is confirmed: login still works without a code.
    assert (await client.post("/api/v1/auth/login", json=login)).status_code == 200
    bad = await client.post("/api/v1/auth/2fa/enable", headers=ana.headers, json={"code": "000000"})
    assert bad.status_code == 400 and bad.json()["code"] == "auth.otp_invalid"
    r = await client.post("/api/v1/auth/2fa/enable", headers=ana.headers, json={"code": totp.now()})
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10

    r = await client.post("/api/v1/auth/login", json=login)
    assert r.status_code == 401 and r.json()["code"] == "auth.otp_required"
    r = await client.post("/api/v1/auth/login", json={**login, "otp_code": "123456"})
    assert r.json()["code"] == "auth.otp_invalid"
    r = await client.post("/api/v1/auth/login", json={**login, "otp_code": totp.now()})
    assert r.status_code == 200 and r.json()["user"]["two_factor"] is True
    # A recovery code works once.
    assert (
        await client.post("/api/v1/auth/login", json={**login, "otp_code": codes[0]})
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/login", json={**login, "otp_code": codes[0]})
    ).status_code == 401

    # Secrets never reach the audit log.
    rows = await session.scalars(select(AuditLog).where(AuditLog.entity == "users"))
    assert all(r.field not in ("totp_secret", "recovery_codes") for r in rows)

    off = {"password": "errada", "code": totp.now()}
    assert (
        await client.post("/api/v1/auth/2fa/disable", headers=ana.headers, json=off)
    ).status_code == 401
    off["password"] = PASSWORD
    assert (
        await client.post("/api/v1/auth/2fa/disable", headers=ana.headers, json=off)
    ).status_code == 204
    assert (await client.post("/api/v1/auth/login", json=login)).status_code == 200
