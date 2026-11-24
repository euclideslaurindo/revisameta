"""AI settings per project (docs/ia.md 7.15.5; docs/modelo-dados.md `ai_settings`)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin, IdMixin, TimestampMixin


class AISettings(BusinessMixin, AuditedMixin, Base):
    """Off by default. Turning it on needs an admin to accept the data-use notice of the
    provider; who accepted, when and which notice version stay here and in the audit
    log. functions: the features allowed in this project (tutor, locate, ...)."""

    __tablename__ = "ai_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(20))
    functions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notice_version: Mapped[str | None] = mapped_column(String(20))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None]
    # Set when a feature is switched off because its accuracy fell below the threshold.
    disabled_functions: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index(
            "uq_ai_settings_project",
            "project_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class AICacheEntry(IdMixin, TimestampMixin, Base):
    """Validated answer for one exact question in one project (docs/ia.md 7.15.5).

    key: SHA-256 of (project, function, prompt version, model, instructions, content).
    Not business data and not audited: it only avoids spending the quota twice.
    """

    __tablename__ = "ai_cache"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    function: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(20))
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (Index("uq_ai_cache_key", "project_id", "key", unique=True),)
