import uuid

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditedMixin, Base, IdMixin, TimestampMixin


class UsageQuota(IdMixin, TimestampMixin, AuditedMixin, Base):
    """Per-user limit override and counters (docs/dominio.md, 6).

    `limit_value` NULL means "use the default from settings". `period` is "total"
    for projects and storage; daily periods (e.g. "2026-11-13") are used for AI later.
    """

    __tablename__ = "usage_quotas"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    period: Mapped[str] = mapped_column(String(16), default="total")
    used: Mapped[int] = mapped_column(BigInteger, default=0)
    limit_value: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (UniqueConstraint("user_id", "kind", "period", name="uq_usage_quotas_key"),)
