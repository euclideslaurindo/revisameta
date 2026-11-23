"""PRISMA 2020 (docs/modulos.md 7.9): manual adjustments of the flow diagram counts."""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class PrismaAdjustment(BusinessMixin, AuditedMixin, Base):
    """A count typed by a person instead of the one the system computes (e.g. a group
    that imported only the final list of studies). Always with a justification; the
    diagram marks adjusted counts and the audit log keeps every change."""

    __tablename__ = "prisma_adjustments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[int] = mapped_column(Integer)
    justification: Mapped[str] = mapped_column(String(1000))


class PrismaChecklistItem(BusinessMixin, AuditedMixin, Base):
    """Where the manuscript reports each PRISMA 2020 item (docs/modulos.md 7.9)."""

    __tablename__ = "prisma_checklist_items"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|reported|not_applicable
    location: Mapped[str | None] = mapped_column(String(500))  # e.g. "Methods, p. 4"
