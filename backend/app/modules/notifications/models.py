"""In-app notifications (docs/modulos.md 7.13; stage 6 step 4)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Notification(IdMixin, TimestampMixin, Base):
    """A message for one user about one project.

    kind: mention | screening_conflict | deadline. payload: what the screen needs to
    build the text and the link (ids and short labels only, never e-mails). key: avoids
    sending the same notice twice (e.g. one conflict, one deadline date).
    Not audited: it is a delivery record, not review data.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None]
