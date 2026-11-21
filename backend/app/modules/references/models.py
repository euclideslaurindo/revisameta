"""Searches imported into a project (docs/modulos.md 7.2; stage 5 step 1).

A search is one file exported from a database (PubMed, LILACS...) with the date and the
strategy used, as the PRISMA flow diagram and the Methods section need them. Its
records become references (studies.models.Reference with search_id).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, String, Text
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
