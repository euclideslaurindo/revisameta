"""Imports every model so Alembic and the mapper registry see all tables."""

from app.modules.audit import recorder as _audit_recorder  # noqa: F401 - registers listener
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.projects.models import Invitation, Project, ProjectMember
from app.modules.quotas.models import UsageQuota

__all__ = [
    "AuditLog",
    "EmailToken",
    "Invitation",
    "Project",
    "ProjectMember",
    "RefreshToken",
    "UsageQuota",
    "User",
]
