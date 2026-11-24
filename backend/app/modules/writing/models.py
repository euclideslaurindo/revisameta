"""Abstract for the congress, edited by the group (docs/modulos.md 7.14)."""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class AbstractDraft(BusinessMixin, AuditedMixin, Base):
    """One live abstract per project, with the congress limits; edits are audited."""

    __tablename__ = "abstract_drafts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    text: Mapped[str] = mapped_column(Text, default="")
    word_limit: Mapped[int | None] = mapped_column(Integer)
    char_limit: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "uq_abstract_drafts_project",
            "project_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )
