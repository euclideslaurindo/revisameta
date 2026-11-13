"""Registration, e-mail verification, login and refresh-token rotation (ADR-006)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotAuthenticatedError
from app.core.i18n import Language, translate
from app.core.security import (
    hash_password,
    hash_token,
    is_strong_password,
    new_opaque_token,
    password_needs_rehash,
    verify_password,
)
from app.db.base import new_id
from app.integrations.email import Email, EmailSender
from app.modules.auth.models import EmailToken, RefreshToken, User

TERMS_VERSION = "2026-11-13"
VERIFY_PURPOSE = "verify_email"
VERIFY_TTL = timedelta(hours=48)


def _now() -> datetime:
    return datetime.now(UTC)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.scalars(select(User).where(func.lower(User.email) == email.lower()))
    return result.first()


async def _send_verification(session: AsyncSession, user: User, sender: EmailSender) -> None:
    token, token_hash = new_opaque_token()
    session.add(
        EmailToken(
            user_id=user.id,
            purpose=VERIFY_PURPOSE,
            token_hash=token_hash,
            expires_at=_now() + VERIFY_TTL,
        )
    )
    await session.commit()
    language: Language = "en" if user.ui_language == "en" else "pt-BR"
    link = f"{get_settings().app_base_url}/verificar-email?token={token}"
    await sender.send(
        Email(
            to=user.email,
            subject=translate("email.verify.subject", language),
            body=translate("email.verify.body", language, name=user.name, link=link),
        )
    )


async def register(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    accept_terms: bool,
    language: Language,
    sender: EmailSender,
) -> User:
    if not accept_terms:
        raise AppError("auth.terms_required", status_code=422)
    if not is_strong_password(password):
        raise AppError("auth.weak_password", status_code=422)
    if await get_user_by_email(session, email) is not None:
        raise AppError("auth.email_taken", status_code=409)

    user = User(
        id=new_id(),
        name=name.strip(),
        email=email.strip(),
        password_hash=hash_password(password),
        ui_language=language,
        terms_version=TERMS_VERSION,
        terms_accepted_at=_now(),
    )
    session.add(user)
    await session.flush()
    await _send_verification(session, user, sender)
    return user


async def resend_verification(session: AsyncSession, email: str, sender: EmailSender) -> None:
    user = await get_user_by_email(session, email)
    if user is not None and user.email_verified_at is None and user.is_active:
        await _send_verification(session, user, sender)


async def verify_email(session: AsyncSession, token: str) -> None:
    record = (
        await session.scalars(
            select(EmailToken).where(
                EmailToken.token_hash == hash_token(token),
                EmailToken.purpose == VERIFY_PURPOSE,
            )
        )
    ).first()
    if record is None or record.used_at is not None or record.expires_at < _now():
        raise AppError("auth.invalid_token", status_code=400)
    user = await session.get(User, record.user_id)
    if user is None:
        raise AppError("auth.invalid_token", status_code=400)
    record.used_at = _now()
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    await session.commit()


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise AppError("auth.invalid_credentials", status_code=401)
    if not user.is_active:
        raise AppError("auth.account_disabled", status_code=403)
    if user.email_verified_at is None:
        raise AppError("auth.email_not_verified", status_code=403)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await session.commit()
    return user


async def issue_refresh_token(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> tuple[str, RefreshToken]:
    token, token_hash = new_opaque_token()
    record = RefreshToken(
        id=new_id(),
        user_id=user_id,
        family_id=family_id or new_id(),
        token_hash=token_hash,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
    )
    session.add(record)
    await session.flush()
    return token, record


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def rotate_refresh_token(session: AsyncSession, token: str | None) -> tuple[str, User]:
    """Exchange a valid refresh token for a new one. Reuse of an old token kills the family."""
    if not token:
        raise NotAuthenticatedError("auth.session_expired")
    record = (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
        )
    ).first()
    if record is None:
        raise NotAuthenticatedError("auth.session_expired")
    if record.revoked_at is not None:
        # A rotated token came back: it may have been stolen. Revoke the whole session.
        await _revoke_family(session, record.family_id)
        await session.commit()
        raise NotAuthenticatedError("auth.session_expired")
    if record.expires_at < _now():
        raise NotAuthenticatedError("auth.session_expired")

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("auth.session_expired")

    new_token, new_record = await issue_refresh_token(session, user.id, record.family_id)
    record.revoked_at = _now()
    record.replaced_by_id = new_record.id
    await session.commit()
    return new_token, user


async def logout(session: AsyncSession, token: str | None) -> None:
    if not token:
        return
    record = (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
        )
    ).first()
    if record is not None:
        await _revoke_family(session, record.family_id)
        await session.commit()
