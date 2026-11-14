import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin, IdMixin, TimestampMixin


class UploadStatus(enum.StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class StoredFile(IdMixin, TimestampMixin, Base):
    """One physical object per distinct content (SHA-256). Only metadata lives here."""

    __tablename__ = "stored_files"

    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(300))
    ref_count: Mapped[int] = mapped_column(Integer, default=1)
    # Filled by the worker (pypdfium2). no_text = scanned PDF without a text layer.
    page_count: Mapped[int | None] = mapped_column(Integer)
    text_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )


class PdfPageText(IdMixin, Base):
    """Text of each page, per physical file (extracted once even if uploaded twice).

    Only reachable through a project's pdf_files row, which carries the project check.
    """

    __tablename__ = "pdf_page_texts"

    stored_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int] = mapped_column(Integer)  # 1-based
    content: Mapped[str] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("stored_file_id", "page", name="uq_pdf_page_texts_page"),)


class UploadSession(BusinessMixin, AuditedMixin, Base):
    """A resumable multipart upload, sent by the browser straight to storage."""

    __tablename__ = "upload_sessions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    part_size: Mapped[int] = mapped_column(BigInteger)
    part_count: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    s3_upload_id: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default=UploadStatus.UPLOADING)
    error_code: Mapped[str | None] = mapped_column(String(64))
    stored_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stored_files.id"))
    job_id: Mapped[uuid.UUID | None]
    expires_at: Mapped[datetime]
