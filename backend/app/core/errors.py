"""Domain errors rendered as Problem Details (RFC 9457), translated per request."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.i18n import negotiate_language, translate

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    """Base domain error. `code` is an i18n key in app.core.i18n.MESSAGES."""

    status_code = 400
    code = "error.internal"

    def __init__(self, code: str | None = None, *, status_code: int | None = None, **params: Any):
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.params = params
        super().__init__(self.code)


class NotFoundError(AppError):
    status_code = 404
    code = "error.not_found"


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "error.not_authenticated"


class ForbiddenError(AppError):
    status_code = 403
    code = "error.forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "error.version_conflict"


class QuotaExceededError(AppError):
    status_code = 403


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "error.stats_unavailable"


def problem(
    request: Request,
    status: int,
    code: str,
    *,
    errors: list[dict[str, Any]] | None = None,
    **params: Any,
) -> JSONResponse:
    language = negotiate_language(request.headers.get("accept-language"))
    body: dict[str, Any] = {
        "type": f"https://revisameta.app/problems/{code}",
        "title": translate(code, language, **params),
        "status": status,
        "code": code,
        "instance": request.url.path,
    }
    if errors:
        body["errors"] = errors
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status_code, exc.code, **exc.params)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, _exc: RateLimitExceeded) -> JSONResponse:
        return problem(request, 429, "error.rate_limited")

    @app.exception_handler(StaleDataError)
    async def _stale(request: Request, _exc: StaleDataError) -> JSONResponse:
        return problem(request, 409, "error.version_conflict")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(err.get("loc", ())), "type": err.get("type"), "msg": err.get("msg")}
            for err in exc.errors()
        ]
        return problem(request, 422, "error.validation", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "error.not_authenticated",
            403: "error.forbidden",
            404: "error.not_found",
            429: "error.rate_limited",
        }.get(exc.status_code, "error.internal")
        return problem(request, exc.status_code, code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", exc_info=exc)
        return problem(request, 500, "error.internal")
