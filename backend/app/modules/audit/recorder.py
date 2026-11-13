"""Writes audit_log rows automatically on every flush of an AuditedMixin model."""

import enum
import uuid
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, UOWTransaction

from app.core.logging import request_id_var
from app.db.base import AuditedMixin, new_id
from app.modules.audit.models import AuditLog

current_user_id_var: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)

_IGNORED_FIELDS = frozenset({"updated_at", "version", "created_at"})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, list | tuple | set):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def _columns(obj: AuditedMixin) -> list[str]:
    mapper = inspect(type(obj))
    excluded = _IGNORED_FIELDS | obj.__audit_exclude__
    return [attr.key for attr in mapper.column_attrs if attr.key not in excluded]


def _row(obj: AuditedMixin, action: str, **kwargs: Any) -> AuditLog:
    return AuditLog(
        id=new_id(),
        project_id=obj.audit_project_id(),
        entity=obj.__tablename__,  # type: ignore[attr-defined]
        entity_id=obj.id,  # type: ignore[attr-defined]
        action=action,
        user_id=current_user_id_var.get(),
        request_id=request_id_var.get(),
        **kwargs,
    )


@event.listens_for(Session, "before_flush")
def _record_changes(session: Session, _ctx: UOWTransaction, _instances: object) -> None:
    for obj in list(session.new):
        if not isinstance(obj, AuditedMixin):
            continue
        if getattr(obj, "id", None) is None:
            obj.id = new_id()  # type: ignore[attr-defined]
        snapshot = {key: _json_safe(getattr(obj, key, None)) for key in _columns(obj)}
        session.add(_row(obj, "create", new_value=snapshot))

    for obj in list(session.dirty):
        if not isinstance(obj, AuditedMixin) or not session.is_modified(obj):
            continue
        state = inspect(obj)
        for key in _columns(obj):
            history = state.attrs[key].history
            if not history.has_changes():
                continue
            old = history.deleted[0] if history.deleted else None
            new = history.added[0] if history.added else None
            if old == new:
                continue
            action = "delete" if key == "deleted_at" and new is not None else "update"
            session.add(
                _row(obj, action, field=key, old_value=_json_safe(old), new_value=_json_safe(new))
            )

    for obj in list(session.deleted):
        if isinstance(obj, AuditedMixin):
            session.add(_row(obj, "delete", field="*"))
