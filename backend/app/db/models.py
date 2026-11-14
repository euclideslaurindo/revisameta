"""Imports every model so Alembic and the mapper registry see all tables."""

from app.modules.audit import recorder as _audit_recorder  # noqa: F401 - registers listener
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.jobs.models import BackgroundJob
from app.modules.projects.models import Invitation, Project, ProjectMember
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.quotas.models import UsageQuota
from app.modules.uploads.models import StoredFile, UploadSession

__all__ = [
    "AuditLog",
    "BackgroundJob",
    "ComparisonGroup",
    "EmailToken",
    "Invitation",
    "Outcome",
    "Project",
    "ProjectMember",
    "RefreshToken",
    "StoredFile",
    "UploadSession",
    "UsageQuota",
    "User",
]
