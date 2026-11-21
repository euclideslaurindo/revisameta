"""Title and abstract screening (docs/modulos.md 7.3; stage 5 step 3).

- ScreeningDecision: one row per decision of a reviewer. Decisions are never edited:
  a new decision supersedes the previous one and "undo" withdraws the latest, so the
  whole history of each reference stays (lesson L6).
- ScreeningResolution: the final decision of a conflict, by an admin, with a reason.
- ScreeningAssignment: batches of references given to specific reviewers (lesson L9).
The result of a reference comes from the decisions (approved rule: two "include" pass,
two "exclude" leave, any other combination, any "maybe" included, is a conflict).
"""

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, BusinessMixin


class ScreeningDecision(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "screening_decisions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    stage: Mapped[str] = mapped_column(String(16), default="title_abstract")
    decision: Mapped[str] = mapped_column(String(8))  # include | exclude | maybe
    note: Mapped[str | None] = mapped_column(String(1000))
    # Withdrawn by "undo" or replaced by a later decision of the same reviewer.
    superseded_at: Mapped[dt.datetime | None] = mapped_column()
    undone: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index(
            "ix_screening_current",
            "reference_id",
            "user_id",
            "stage",
            postgresql_where="superseded_at IS NULL AND deleted_at IS NULL",
        ),
    )


class ScreeningResolution(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "screening_resolutions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16), default="title_abstract")
    decision: Mapped[str] = mapped_column(String(8))  # include | exclude
    reason: Mapped[str] = mapped_column(String(1000))


class ScreeningAssignment(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "screening_assignments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16), default="title_abstract")
