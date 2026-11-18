"""Saved analyses (docs/modelo-dados.md, `analysis`; docs/modulos.md 7.7 reproducibility)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class Analysis(BusinessMixin, AuditedMixin, Base):
    """One run of the model, kept with everything needed to reproduce it.

    - input_snapshot: the request sent to R (yi, vi per study) and every study row of
      the assembly (who entered, why the others did not, conversions used).
    - sources: consensus extraction id, data_version and status of every study when it
      ran; any difference later marks the analysis as outdated (7.5.1 item 18).
    - result / r_meta: what R returned, with R and package versions.
    """

    __tablename__ = "analyses"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    outcome_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outcomes.id"))
    timepoint: Mapped[str] = mapped_column(String(60))
    measure: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(8))
    test: Mapped[str] = mapped_column(String(8))
    data_set: Mapped[str] = mapped_column(String(16))
    k: Mapped[int] = mapped_column(Integer)
    planned: Mapped[bool] = mapped_column(Boolean)
    not_planned: Mapped[list[str]] = mapped_column(JSONB, default=list)
    included_study_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    r_meta: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(String(500))
