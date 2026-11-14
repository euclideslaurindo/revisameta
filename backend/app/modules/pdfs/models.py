import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class PdfFile(BusinessMixin, AuditedMixin, Base):
    """A PDF attached to a report (article). The bytes live once in stored_files."""

    __tablename__ = "pdf_files"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id"), index=True)
    stored_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_files.id"))
    upload_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_sessions.id"))
    original_filename: Mapped[str] = mapped_column(String(255))


class PdfAnnotation(BusinessMixin, AuditedMixin, Base):
    """A marked passage: the source of an extracted number or of a judgement."""

    __tablename__ = "pdf_annotations"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    pdf_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pdf_files.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    page: Mapped[int] = mapped_column(Integer)
    # Rectangles relative to the page (0..1), so they survive zoom: [{x, y, w, h}, ...]
    rects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    quote: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(16), default="yellow")
