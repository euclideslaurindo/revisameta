"""Imports every model so Alembic and the mapper registry see all tables."""

from app.modules.audit import recorder as _audit_recorder  # noqa: F401 - registers listener
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.extraction.models import (
    CheckAlert,
    Extraction,
    ExtractionDecision,
    ExtractionForm,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.jobs.models import BackgroundJob
from app.modules.pdfs.models import PdfAnnotation, PdfFile
from app.modules.projects.models import Invitation, Project, ProjectMember, StageEvent
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.quotas.models import UsageQuota
from app.modules.risk_of_bias.models import (
    RobAnswer,
    RobAssessment,
    RobDecision,
    RobJudgement,
    RobStudyTool,
    RobTool,
)
from app.modules.studies.models import Reference, Report, Study
from app.modules.uploads.models import PdfPageText, StoredFile, UploadSession

__all__ = [
    "AuditLog",
    "BackgroundJob",
    "CheckAlert",
    "ComparisonGroup",
    "EmailToken",
    "Extraction",
    "ExtractionDecision",
    "ExtractionForm",
    "Invitation",
    "Outcome",
    "OutcomeData",
    "OutcomeMeasure",
    "PdfAnnotation",
    "PdfFile",
    "PdfPageText",
    "Project",
    "ProjectMember",
    "Reference",
    "RefreshToken",
    "Report",
    "RobAnswer",
    "RobAssessment",
    "RobDecision",
    "RobJudgement",
    "RobStudyTool",
    "RobTool",
    "StageEvent",
    "StoredFile",
    "Study",
    "StudyArm",
    "UploadSession",
    "UsageQuota",
    "User",
]
