"""Imports every model so Alembic and the mapper registry see all tables."""

from app.modules.audit import recorder as _audit_recorder  # noqa: F401 - registers listener
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailToken, RefreshToken, User

__all__ = ["AuditLog", "EmailToken", "RefreshToken", "User"]
