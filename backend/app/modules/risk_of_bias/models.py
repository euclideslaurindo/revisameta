"""Risk-of-bias tables (docs/modelo-dados-etapa2.md)."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class RobTool(BusinessMixin, AuditedMixin, Base):
    """An instrument enabled in a project: a frozen copy of a catalog template.

    Assessments point to this copy, so the version used is always recorded (lesson L3).
    """

    __tablename__ = "rob_tools"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(40))
    family: Mapped[str] = mapped_column(String(16))
    template_version: Mapped[str] = mapped_column(String(40))
    structure: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Official wording pasted by the admin, by "domain.question" key.
    texts: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    # JBI/NOS/generic: the group's rule for the overall judgement (empty = free).
    overall_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "uq_rob_tools_project_template_version",
            "project_id",
            "template_key",
            "template_version",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class RobStudyTool(BusinessMixin, AuditedMixin, Base):
    """The instrument chosen for a study (suggested by its design, confirmed by the admin)."""

    __tablename__ = "rob_study_tools"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rob_tools.id"))
    confirmed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index(
            "uq_rob_study_tools_study",
            "study_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )
