"""Studies and reports (docs/modulos.md 7.2 and 7.4; docs/modelo-dados-etapa1.md).

A study is a group of patients/cohort; a report is one published article about it.
Several reports can belong to the same study, so the same patients are never counted twice.
"""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class StudyDesign(enum.StrEnum):
    RCT = "rct"
    COHORT_PROSPECTIVE = "cohort_prospective"
    COHORT_RETROSPECTIVE = "cohort_retrospective"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_SERIES = "case_series"
    OTHER = "other"


class Reference(BusinessMixin, AuditedMixin, Base):
    """Bibliographic record. Search import and screening complete it in Etapa 5."""

    __tablename__ = "references"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(255))  # normalized, lower case
    pmid: Mapped[str | None] = mapped_column(String(20))
    journal: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        Index(
            "uq_references_project_doi",
            "project_id",
            "doi",
            unique=True,
            postgresql_where="deleted_at IS NULL AND doi IS NOT NULL",
        ),
    )


class Study(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "studies"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))  # e.g. "Ballet 2025"
    design: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_studies_project_label",
            "project_id",
            "label",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )


class Report(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "reports"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"), index=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        # An article belongs to a single study (no double counting).
        Index(
            "uq_reports_reference",
            "reference_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )
