"""Declarative base and mixins shared by every business table (docs/modelo-dados.md, 9)."""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from uuid_utils.compat import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id() -> uuid.UUID:
    """UUID v7: time-ordered, index friendly."""
    return uuid7()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CreatedByMixin:
    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class SoftDeleteMixin:
    """Rows are never hard-deleted; queries hide them unless `include_deleted` is set."""

    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class VersionedMixin:
    """Optimistic locking: concurrent edits raise StaleDataError (HTTP 409)."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.__table__.c.version}  # type: ignore[attr-defined]


class AuditedMixin:
    """Every insert/update/delete of these models is written to audit_log."""

    __audit_exclude__: ClassVar[frozenset[str]] = frozenset()

    def audit_project_id(self) -> uuid.UUID | None:
        return getattr(self, "project_id", None)


class BusinessMixin(IdMixin, TimestampMixin, CreatedByMixin, SoftDeleteMixin, VersionedMixin):
    """Standard columns: id, created_at, updated_at, created_by, deleted_at, version."""
