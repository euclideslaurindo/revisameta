"""Data extraction (docs/modulos.md 7.5; docs/modelo-dados-etapa1.md).

Each study has up to two individual extractions (one per extractor, blind to each
other) and one consensus. Analyses and exports read only the consensus (bloco G).
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class ExtractionKind(enum.StrEnum):
    INDIVIDUAL = "individual"
    CONSENSUS = "consensus"


class ExtractionStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    LOCKED = "locked"


class ValueType(enum.StrEnum):
    FINAL = "final"
    CHANGE = "change"


class DispersionType(enum.StrEnum):
    SD = "sd"
    SE = "se"
    CI95 = "ci95"
    IQR = "iqr"
    RANGE = "range"
    NOT_REPORTED = "not_reported"


class DataSource(enum.StrEnum):
    ARTICLE = "article"
    AUTHOR = "author"
    DIGITIZER = "digitizer"
    AI = "ai"


class ExtractionForm(BusinessMixin, AuditedMixin, Base):
    """Versioned characteristics form. Changing it creates a new version."""

    __tablename__ = "extraction_forms"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    form_version: Mapped[int] = mapped_column(Integer)
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class Extraction(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "extractions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"), index=True)
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_forms.id"))
    extractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=ExtractionStatus.DRAFT)
    characteristics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Goes up on every change to numbers (arms, scales, outcome data). Etapa 3 marks
    # analyses as outdated when the consensus version they used is no longer current.
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    # Who submitted it: for the consensus, the admin who checked it (final review).
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_extractions_individual",
            "study_id",
            "extractor_id",
            unique=True,
            postgresql_where="deleted_at IS NULL AND kind = 'individual'",
        ),
        Index(
            "uq_extractions_consensus",
            "study_id",
            unique=True,
            postgresql_where="deleted_at IS NULL AND kind = 'consensus'",
        ),
    )


class StudyArm(BusinessMixin, AuditedMixin, Base):
    """A group as the study reports it; mapped to a protocol comparison group."""

    __tablename__ = "study_arms"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    n: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    mapped_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comparison_groups.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)


class OutcomeMeasure(BusinessMixin, AuditedMixin, Base):
    """Scale used by this study for an outcome (range and direction)."""

    __tablename__ = "outcome_measures"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    outcome_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outcomes.id"))
    scale_name: Mapped[str | None] = mapped_column(String(200))
    scale_min: Mapped[Decimal | None] = mapped_column(Numeric)
    scale_max: Mapped[Decimal | None] = mapped_column(Numeric)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index(
            "uq_outcome_measures_extraction_outcome",
            "extraction_id",
            "outcome_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class OutcomeData(BusinessMixin, AuditedMixin, Base):
    """The numbers of one outcome, for one arm, at one time point."""

    __tablename__ = "outcome_data"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    arm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_arms.id"))
    outcome_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outcomes.id"))
    timepoint: Mapped[str] = mapped_column(String(60))
    value_type: Mapped[str] = mapped_column(String(16), default=ValueType.FINAL)

    n: Mapped[int | None] = mapped_column(Integer)
    mean: Mapped[Decimal | None] = mapped_column(Numeric)
    dispersion_type: Mapped[str | None] = mapped_column(String(16))
    dispersion_source: Mapped[str | None] = mapped_column(String(300))
    sd: Mapped[Decimal | None] = mapped_column(Numeric)
    se: Mapped[Decimal | None] = mapped_column(Numeric)
    ci_low: Mapped[Decimal | None] = mapped_column(Numeric)
    ci_high: Mapped[Decimal | None] = mapped_column(Numeric)
    median: Mapped[Decimal | None] = mapped_column(Numeric)
    q1: Mapped[Decimal | None] = mapped_column(Numeric)
    q3: Mapped[Decimal | None] = mapped_column(Numeric)
    min: Mapped[Decimal | None] = mapped_column(Numeric)
    max: Mapped[Decimal | None] = mapped_column(Numeric)
    events: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[int | None] = mapped_column(Integer)
    t_stat: Mapped[Decimal | None] = mapped_column(Numeric)
    p_value: Mapped[Decimal | None] = mapped_column(Numeric)
    effect_reported: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    adjusted_for: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(String(16), default=DataSource.ARTICLE)
    source_location: Mapped[str | None] = mapped_column(String(300))
    annotation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pdf_annotations.id"))
    direction_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertStatus(enum.StrEnum):
    OPEN = "open"
    JUSTIFIED = "justified"
    RESOLVED = "resolved"


class CheckAlert(BusinessMixin, AuditedMixin, Base):
    """An extraction safeguard alert (docs/modulos.md 7.5.1).

    Recomputed whenever the extraction is read for review: alerts that no longer apply
    become `resolved`; a justified alert reopens if the values behind it change.
    """

    __tablename__ = "check_alerts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(8))
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[uuid.UUID]
    field: Mapped[str | None] = mapped_column(String(120))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.OPEN)
    justification: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class DecisionChoice(enum.StrEnum):
    A = "a"  # first extractor's value
    B = "b"  # second extractor's value
    CONSENSUS = "consensus"  # keep the value typed in the consensus (justified)


class ExtractionDecision(BusinessMixin, AuditedMixin, Base):
    """How one divergence between the two extractors was settled in the consensus."""

    __tablename__ = "extraction_decisions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    consensus_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(300))
    choice: Mapped[str] = mapped_column(String(16))
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index(
            "uq_extraction_decisions_item",
            "consensus_id",
            "item_key",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )
