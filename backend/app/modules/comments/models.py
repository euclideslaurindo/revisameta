"""Comments on a study, reference or analysis, optionally on one field (docs/modulos.md 7.13)."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class Comment(BusinessMixin, AuditedMixin, Base):
    """entity: study | reference | analysis; field: optional key (e.g. "group1.sd").
    mentions: ids of project members chosen by the author (notified in step 4).
    Removing a comment is a soft delete; edits are audited."""

    __tablename__ = "comments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    entity: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(String(4000))
    mentions: Mapped[list[str]] = mapped_column(JSONB, default=list)
