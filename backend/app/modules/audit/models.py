import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin


class AuditLog(IdMixin, Base):
    """Append-only history of every change (docs/modulos.md, 7.12)."""

    __tablename__ = "audit_log"

    project_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(String(16))  # create | update | delete
    field: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (Index("ix_audit_log_entity", "entity", "entity_id"),)
