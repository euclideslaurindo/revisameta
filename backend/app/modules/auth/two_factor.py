"""Optional two-factor authentication with an authenticator app (TOTP, RFC 6238;
docs/riscos.md 10.1, P2; stage 8 step 7).

- Setup creates a secret and shows it (and an otpauth:// link) once; 2FA only turns on
  after the person types a valid code, so a mistyped secret never locks anyone out.
- Turning it on returns 10 one-use recovery codes, stored only as SHA-256 hashes.
- At login, an account with 2FA must send the current code (a 30-second window either
  side is accepted, for clock drift) or one recovery code, which is then spent.
- Turning it off needs the password and a current code (or a recovery code).
The secret and the codes never reach the audit log.
"""

import hashlib
import secrets
from datetime import UTC, datetime

import pyotp
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import verify_password
from app.modules.auth.models import User

ISSUER = "RevisaMeta"
RECOVERY_CODES = 10


class SetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class DisableIn(CodeIn):
    password: str = Field(min_length=1, max_length=256)


class RecoveryOut(BaseModel):
    recovery_codes: list[str]


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace(" ", "").encode()).hexdigest()


def _new_codes() -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODES)]


def check(user: User, code: str | None) -> bool:
    """True when `code` is the current TOTP or an unused recovery code (spent here)."""
    if not code or not user.totp_secret:
        return False
    digits = code.replace(" ", "")
    if digits.isdigit() and pyotp.TOTP(user.totp_secret).verify(digits, valid_window=1):
        return True
    hashed = _hash(code)
    if hashed in (user.recovery_codes or []):
        user.recovery_codes = [h for h in user.recovery_codes if h != hashed]
        return True
    return False


async def setup(session: AsyncSession, user: User) -> SetupOut:
    if user.totp_enabled_at is not None:
        raise AppError("auth.2fa_already_on", status_code=409)
    user.totp_secret = pyotp.random_base32()
    await session.commit()
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return SetupOut(secret=user.totp_secret, otpauth_uri=uri)


async def enable(session: AsyncSession, user: User, data: CodeIn) -> RecoveryOut:
    if user.totp_enabled_at is not None:
        raise AppError("auth.2fa_already_on", status_code=409)
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(
        data.code.replace(" ", ""), valid_window=1
    ):
        raise AppError("auth.otp_invalid", status_code=400)
    codes = _new_codes()
    user.recovery_codes = [_hash(c) for c in codes]
    user.totp_enabled_at = datetime.now(UTC)
    await session.commit()
    return RecoveryOut(recovery_codes=codes)


async def disable(session: AsyncSession, user: User, data: DisableIn) -> None:
    if user.totp_enabled_at is None:
        raise AppError("auth.2fa_not_on", status_code=409)
    if not verify_password(user.password_hash, data.password):
        raise AppError("auth.invalid_credentials", status_code=401)
    if not check(user, data.code):
        raise AppError("auth.otp_invalid", status_code=400)
    user.totp_secret = None
    user.totp_enabled_at = None
    user.recovery_codes = []
    await session.commit()


def require_at_login(user: User, code: str | None) -> None:
    if user.totp_enabled_at is None:
        return
    if not code:
        raise AppError("auth.otp_required", status_code=401)
    if not check(user, code):
        raise AppError("auth.otp_invalid", status_code=401)
