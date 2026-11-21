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
    # Full text: excluding needs a reason (it goes to the PRISMA flow diagram).
    exclusion_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exclusion_reasons.id")
    )
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
    exclusion_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exclusion_reasons.id")
    )


class ScreeningAssignment(BusinessMixin, AuditedMixin, Base):
    __tablename__ = "screening_assignments"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("references.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16), default="title_abstract")


class ExclusionReason(BusinessMixin, AuditedMixin, Base):
    """Reason to exclude an article at full text (docs/modulos.md 7.4; lesson L5).

    The project starts with a standard list (key set, label empty: the screen shows the
    translation). The admin renames (label), adds, removes reasons nobody used, and
    merges one reason into another (merged_into_id); every change is in the audit log.
    """

    __tablename__ = "exclusion_reasons"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str | None] = mapped_column(String(40))  # standard reasons only
    label: Mapped[str | None] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(default=0)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exclusion_reasons.id"))
