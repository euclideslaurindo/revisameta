import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.rate_limit import limiter
from app.db import models as _models  # noqa: F401 - register mappers and audit listener
from app.db.session import dispose_engine
from app.integrations.storage import Storage
from app.modules.analysis.router import router as analysis_router
from app.modules.auth.router import router as auth_router
from app.modules.backup.router import router as backup_router
from app.modules.comments.router import router as comments_router
from app.modules.exports.router import router as exports_router
from app.modules.extraction.router import router as extraction_router
from app.modules.grade.router import router as grade_router
from app.modules.jobs.router import router as jobs_router
from app.modules.notifications.router import router as notifications_router
from app.modules.pdfs.router import router as pdfs_router
from app.modules.prisma.router import router as prisma_router
from app.modules.projects.router import router as projects_router
from app.modules.protocol.router import router as protocol_router
from app.modules.quotas.router import router as quotas_router
from app.modules.references.router import router as references_router
from app.modules.risk_of_bias.router import router as rob_router
from app.modules.screening.router import router as screening_router
from app.modules.studies.router import router as studies_router
from app.modules.system.router import router as system_router
from app.modules.uploads.router import router as uploads_router

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.is_production and settings.jwt_secret in ("", "change-me"):
        raise RuntimeError("JWT_SECRET must be set in production")
    try:
        await Storage().ensure_bucket()
    except Exception as exc:  # storage may start later; uploads will report it
        logger.warning("storage_bucket_check_failed", extra={"extra_fields": {"error": str(exc)}})
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="RevisaMeta API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
        # Readable operation ids -> readable generated client (login, createProject...).
        generate_unique_id_function=lambda route: route.name,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    hosts = [*settings.allowed_hosts, "backend", "testserver"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(RequestIdMiddleware)

    app.state.limiter = limiter
    register_error_handlers(app)
    for router in (
        system_router,
        auth_router,
        backup_router,
        projects_router,
        protocol_router,
        studies_router,
        references_router,
        screening_router,
        prisma_router,
        pdfs_router,
        extraction_router,
        exports_router,
        rob_router,
        analysis_router,
        grade_router,
        comments_router,
        notifications_router,
        quotas_router,
        uploads_router,
        jobs_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
