"""Minimal protocol needed by extraction: outcomes and comparison groups (docs/modulos.md, 7.1)."""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class OutcomeType(enum.StrEnum):
    CONTINUOUS = "continuous"
    DICHOTOMOUS = "dichotomous"


class Outcome(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "outcomes"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))
    # Default direction; each study's scale can say otherwise (outcome_measures).
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    timepoints: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index(
            "uq_outcomes_project_name",
            "project_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class ComparisonGroup(BusinessMixin, AuditedMixin, Base):
    """E.g. "Surgery < 5 years" vs "Surgery >= 5 years", with the cut-off rule."""

    __tablename__ = "comparison_groups"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    rule_description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index(
            "uq_comparison_groups_project_label",
            "project_id",
            "label",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )
