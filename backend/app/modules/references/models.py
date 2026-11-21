"""Searches imported into a project (docs/modulos.md 7.2; stage 5 step 1).

A search is one file exported from a database (PubMed, LILACS...) with the date and the
strategy used, as the PRISMA flow diagram and the Methods section need them. Its
records become references (studies.models.Reference with search_id).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class Search(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "searches"
    __audit_exclude__ = frozenset({"errors"})

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    database: Mapped[str] = mapped_column(String(100))
    search_date: Mapped[dt.date] = mapped_column(Date)
    strategy: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(8))  # ris | nbib | bibtex | csv
    storage_key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("background_jobs.id"))
    record_count: Mapped[int] = mapped_column(Integer, default=0)  # references created
    error_count: Mapped[int] = mapped_column(Integer, default=0)  # records not imported
    warning_count: Mapped[int] = mapped_column(Integer, default=0)  # a field left empty
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # first 200
    error_code: Mapped[str | None] = mapped_column(String(64))


class DuplicatePair(BusinessMixin, AuditedMixin, Base):
    """Two imported references that may be the same record (docs/modulos.md 7.2, L4).

    kind: certain (same DOI or PMID) | probable (every criterion together) | related
    (looks alike but differs in numbers, "Part 1/2", erratum, comment, reply...; never a
    duplicate, shown because an erratum may matter).
    status: pending | confirmed | rejected. Only a person confirms; confirming points
    the removed reference to the kept one (Reference.duplicate_of) and is reversible.
    criteria: what matched, with the title score, shown beside the two records.
    """

    __tablename__ = "duplicate_pairs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    reference_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB)
    score: Mapped[float] = mapped_column(Float)  # title similarity, 0..1
    status: Mapped[str] = mapped_column(String(10), default="pending")
    kept_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("references.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[dt.datetime | None] = mapped_column()
