"""Imports every model so Alembic and the mapper registry see all tables."""

from app.modules.ai.models import AICacheEntry, AISettings
from app.modules.analysis.models import Analysis, NarrativeEntry
from app.modules.audit import recorder as _audit_recorder  # noqa: F401 - registers listener
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.comments.models import Comment
from app.modules.extraction.models import (
    CheckAlert,
    Extraction,
    ExtractionDecision,
    ExtractionForm,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.grade.models import GradeAssessment
from app.modules.jobs.models import BackgroundJob
from app.modules.notifications.models import Notification
from app.modules.pdfs.models import PdfAnnotation, PdfFile
from app.modules.prisma.models import PrismaAdjustment, PrismaChecklistItem
from app.modules.projects.models import Invitation, Project, ProjectMember, StageEvent
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.quotas.models import UsageQuota
from app.modules.references.models import DuplicatePair, Search
from app.modules.risk_of_bias.models import (
    RobAnswer,
    RobAssessment,
    RobDecision,
    RobJudgement,
    RobStudyTool,
    RobTool,
)
from app.modules.screening.models import (
    ExclusionReason,
    ScreeningAssignment,
    ScreeningDecision,
    ScreeningResolution,
)
from app.modules.studies.models import Reference, Report, Study
from app.modules.uploads.models import PdfPageText, StoredFile, UploadSession

__all__ = [
    "AICacheEntry",
    "AISettings",
    "Analysis",
    "AuditLog",
    "BackgroundJob",
    "CheckAlert",
    "Comment",
    "ComparisonGroup",
    "DuplicatePair",
    "EmailToken",
    "ExclusionReason",
    "Extraction",
    "ExtractionDecision",
    "ExtractionForm",
    "GradeAssessment",
    "Invitation",
    "NarrativeEntry",
    "Notification",
    "Outcome",
    "OutcomeData",
    "OutcomeMeasure",
    "PdfAnnotation",
    "PdfFile",
    "PdfPageText",
    "PrismaAdjustment",
    "PrismaChecklistItem",
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
    "ScreeningAssignment",
    "ScreeningDecision",
    "ScreeningResolution",
    "Search",
    "StageEvent",
    "StoredFile",
    "Study",
    "StudyArm",
    "UploadSession",
    "UsageQuota",
    "User",
]
