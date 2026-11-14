"""Risk-of-bias tables (docs/modelo-dados-etapa2.md)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
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


class RobAssessment(BusinessMixin, AuditedMixin, Base):
    """One risk-of-bias assessment of a study (or of one result: outcome + time point).

    Individual assessments are blind to other reviewers until the consensus step.
    """

    __tablename__ = "rob_assessments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rob_tools.id"))
    # Per-result instruments (RoB 2, ROBINS): the outcome and time point assessed.
    outcome_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outcomes.id"))
    timepoint: Mapped[str | None] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(16))  # individual | consensus | imported
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Variant chosen for domains that have them (e.g. ROBINS-I V2 domain 1: "A" or "B").
    variants: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RobAnswer(BusinessMixin, AuditedMixin, Base):
    """Answer to one signalling question (per outcome or result when the question asks so)."""

    __tablename__ = "rob_answers"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rob_assessments.id"), index=True)
    question_key: Mapped[str] = mapped_column(String(80))  # "domain.question"
    outcome_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outcomes.id"))
    timepoint: Mapped[str | None] = mapped_column(String(60))
    answer: Mapped[str | None] = mapped_column(String(8))
    justification: Mapped[str | None] = mapped_column(Text)
    annotation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pdf_annotations.id"))


class RobJudgement(BusinessMixin, AuditedMixin, Base):
    """Judgement of a domain (domain_key) or overall (domain_key NULL)."""

    __tablename__ = "rob_judgements"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rob_assessments.id"), index=True)
    domain_key: Mapped[str | None] = mapped_column(String(40))
    final: Mapped[str | None] = mapped_column(String(32))
    # Suggestion shown when the reviewer decided (kept for the record and the audit).
    suggested: Mapped[str | None] = mapped_column(String(32))
    justification: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str | None] = mapped_column(String(40))
