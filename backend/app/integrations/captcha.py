"""Cloudflare Turnstile verification (free). Disabled with TURNSTILE_ENABLED=false."""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class CaptchaVerifier:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def verify(self, token: str | None, remote_ip: str | None) -> bool:
        settings = get_settings()
        if not settings.turnstile_enabled:
            return True
        if not token:
            return False
        data = {"secret": settings.turnstile_secret_key, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.post(VERIFY_URL, data=data)
                return bool(response.json().get("success"))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("captcha_verify_failed", extra={"extra_fields": {"error": str(exc)}})
            return False


def get_captcha_verifier() -> CaptchaVerifier:
    return CaptchaVerifier()
