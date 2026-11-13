"""Outgoing e-mail. Development uses Mailpit; tests swap in an in-memory outbox."""

import logging
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpEmailSender:
    async def send(self, email: Email) -> None:
        settings = get_settings()
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password or None,
                start_tls=settings.smtp_tls,
                timeout=15,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            # The account/invitation still exists; the user can ask to resend.
            logger.warning("email_send_failed", extra={"extra_fields": {"error": str(exc)}})


@dataclass
class InMemoryEmailSender:
    outbox: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.outbox.append(email)


_sender: EmailSender = SmtpEmailSender()


def get_email_sender() -> EmailSender:
    return _sender
