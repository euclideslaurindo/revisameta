import enum
import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class Role(enum.StrEnum):
    """Project roles (docs/dominio.md, 6). A member may hold several."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    EXTRACTOR = "extractor"
    STATISTICIAN = "statistician"
    READER = "reader"


class Project(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "projects"

    title: Mapped[str] = mapped_column(String(300))
    question: Mapped[str | None] = mapped_column(Text)
    pico: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prospero: Mapped[str | None] = mapped_column(String(64))
    deadline: Mapped[date | None]
    report_language: Mapped[str] = mapped_column(String(8), default="pt-BR")
    analysis_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    locked_stages: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    # Owner: the creator until administration is transferred. Cannot be removed.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    def audit_project_id(self) -> uuid.UUID | None:
        return self.id


class ProjectMember(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(32)))

    __table_args__ = (
        Index(
            "uq_project_members_active",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class Invitation(BusinessMixin, AuditedMixin, Base):
    """Invitation link with expiry. E-mail is optional: the admin can copy the link."""

    __tablename__ = "invitations"
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset({"token_hash"})

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
