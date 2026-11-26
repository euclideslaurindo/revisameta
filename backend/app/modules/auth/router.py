from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.i18n import negotiate_language
from app.core.rate_limit import (
    CAPTCHA_AFTER_FAILURES,
    clear_failed_logins,
    failed_logins,
    limiter,
    register_failed_login,
)
from app.core.security import create_access_token
from app.db.session import get_session
from app.integrations.captcha import CaptchaVerifier, get_captcha_verifier
from app.integrations.email import EmailSender, get_email_sender
from app.modules.auth import service, two_factor
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AcceptTermsIn,
    ChangePasswordIn,
    EmailIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
    TokenOut,
    UserOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "rm_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _token_out(user: User) -> TokenOut:
    access_token, expires_in = create_access_token(user.id)
    return TokenOut(
        access_token=access_token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().register_rate_limit)
async def register(
    request: Request,
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
    sender: EmailSender = Depends(get_email_sender),
    captcha: CaptchaVerifier = Depends(get_captcha_verifier),
) -> UserOut:
    """Create an account. A verification link is sent by e-mail."""
    if not await captcha.verify(body.captcha_token, _client_ip(request)):
        raise AppError("auth.captcha_failed", status_code=400)
    language = body.language or negotiate_language(request.headers.get("accept-language"))
    user = await service.register(
        session,
        name=body.name,
        email=body.email,
        password=body.password,
        accept_terms=body.accept_terms,
        language=language,
        sender=sender,
    )
    return UserOut.model_validate(user)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: TokenIn, session: AsyncSession = Depends(get_session)) -> None:
    await service.verify_email(session, body.token)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    body: EmailIn,
    session: AsyncSession = Depends(get_session),
    sender: EmailSender = Depends(get_email_sender),
) -> None:
    """Always 204, so the answer does not reveal whether the e-mail has an account."""
    await service.resend_verification(session, body.email, sender)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: EmailIn,
    session: AsyncSession = Depends(get_session),
    sender: EmailSender = Depends(get_email_sender),
) -> None:
    """Always 204, so the answer does not reveal whether the e-mail has an account."""
    await service.request_password_reset(session, body.email, sender)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def reset_password(
    request: Request, body: ResetPasswordIn, session: AsyncSession = Depends(get_session)
) -> None:
    """Set a new password from the e-mailed link; every session is signed out."""
    await service.reset_password(session, body.token, body.password)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    rm_refresh: str | None = Cookie(default=None),
) -> None:
    """Change the password with the current one; other devices are signed out."""
    family = await service.refresh_family(session, rm_refresh)
    await service.change_password(session, user, body.current_password, body.new_password, family)


@router.post("/login")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def login(
    request: Request,
    response: Response,
    body: LoginIn,
    session: AsyncSession = Depends(get_session),
    captcha: CaptchaVerifier = Depends(get_captcha_verifier),
) -> TokenOut:
    """Sign in. After repeated failures for the same e-mail, a captcha is required."""
    if await failed_logins(body.email) >= CAPTCHA_AFTER_FAILURES and not await captcha.verify(
        body.captcha_token, _client_ip(request)
    ):
        raise AppError("auth.captcha_failed", status_code=400)
    try:
        user = await service.authenticate(session, body.email, body.password)
        two_factor.require_at_login(user, body.otp_code)
    except AppError as exc:
        if exc.code in ("auth.invalid_credentials", "auth.otp_invalid"):
            await register_failed_login(body.email)
        raise
    await clear_failed_logins(body.email)
    refresh_token, _ = await service.issue_refresh_token(session, user.id)
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return _token_out(user)


@router.post("/refresh")
async def refresh(
    response: Response,
    session: AsyncSession = Depends(get_session),
    rm_refresh: str | None = Cookie(default=None),
) -> TokenOut:
    """Exchange the refresh cookie for a new access token (and a new refresh cookie)."""
    new_token, user = await service.rotate_refresh_token(session, rm_refresh)
    _set_refresh_cookie(response, new_token)
    return _token_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_session),
    rm_refresh: str | None = Cookie(default=None),
) -> None:
    await service.logout(session, rm_refresh)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me")
async def update_me(
    body: UserUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    if body.name is not None:
        user.name = body.name.strip()
    if body.ui_language is not None:
        user.ui_language = body.ui_language
    await session.commit()
    return UserOut.model_validate(user)


@router.post("/accept-terms")
async def accept_terms(
    body: AcceptTermsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    """Accept the current terms of use and privacy policy (version shown in public-config)."""
    return UserOut.model_validate(await service.accept_terms(session, user, body.version))


@router.post("/2fa/setup")
async def two_factor_setup(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> two_factor.SetupOut:
    """Creates the secret for the authenticator app; 2FA turns on only after a valid code."""
    return await two_factor.setup(session, user)


@router.post("/2fa/enable")
async def two_factor_enable(
    body: two_factor.CodeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> two_factor.RecoveryOut:
    """Confirms the first code; returns 10 one-use recovery codes (shown only now)."""
    return await two_factor.enable(session, user, body)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(
    body: two_factor.DisableIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Turns 2FA off with the password and a current code (or a recovery code)."""
    await two_factor.disable(session, user, body)
