import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    AuditedMixin,
    Base,
    IdMixin,
    SoftDeleteMixin,
    TimestampMixin,
    VersionedMixin,
)


class User(IdMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin, AuditedMixin, Base):
    __tablename__ = "users"
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset({"password_hash"})

    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None]
    ui_language: Mapped[str] = mapped_column(String(8), default="pt-BR")
    terms_version: Mapped[str | None] = mapped_column(String(32))
    terms_accepted_at: Mapped[datetime | None]

    __table_args__ = (
        Index(
            "uq_users_email_active",
            func.lower(email),
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    def audit_project_id(self) -> uuid.UUID | None:
        return None


class RefreshToken(IdMixin, Base):
    """Rotating refresh tokens. Reusing a rotated token revokes the whole family."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EmailToken(IdMixin, Base):
    """Single-use tokens sent by e-mail (verification; later password reset)."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
