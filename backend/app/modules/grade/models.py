"""GRADE certainty of the evidence (docs/modulos.md 7.8; stage 6 step 1)."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class GradeAssessment(BusinessMixin, AuditedMixin, Base):
    """Certainty of one result (outcome + timepoint), decided by people.

    - approach: classic (observational studies start at low) or robins_i (start at
      high when risk of bias was judged with ROBINS-I); recorded as the group chose.
    - analysis: the settings of the analysis the judgement is based on (measure,
      data set, model, risk-of-bias tool), so suggestions can be computed again.
    - domains: {key: {"change": int, "justification": str}} for the five reasons to
      rate down and the three to rate up.
    - suggestions: what the system suggested when the group last saved (a hint only).
    """

    __tablename__ = "grade_assessments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    outcome_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outcomes.id"))
    timepoint: Mapped[str] = mapped_column(String(60))
    approach: Mapped[str] = mapped_column(String(16))
    start_certainty: Mapped[str] = mapped_column(String(10))
    final_certainty: Mapped[str] = mapped_column(String(10))
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    domains: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    suggestions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(String(2000))
