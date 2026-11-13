from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import NotFoundError, QuotaExceededError, register_error_handlers
from app.core.i18n import MESSAGES, negotiate_language, translate
from app.core.logging import RequestIdMiddleware


def test_every_message_exists_in_both_languages() -> None:
    assert set(MESSAGES["pt-BR"]) == set(MESSAGES["en"])


def test_messages_use_the_same_placeholders_in_both_languages() -> None:
    import string

    def fields(text: str) -> set[str]:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}

    for code, pt in MESSAGES["pt-BR"].items():
        assert fields(pt) == fields(MESSAGES["en"][code]), code


def test_language_negotiation() -> None:
    assert negotiate_language(None) == "pt-BR"
    assert negotiate_language("en-US,en;q=0.9") == "en"
    assert negotiate_language("pt-PT") == "pt-BR"
    assert negotiate_language("fr-FR,en;q=0.5") == "en"
    assert negotiate_language("de") == "pt-BR"


def test_translate_formats_params_and_falls_back() -> None:
    assert "7" in translate("quota.projects_exceeded", "en", limit=7)
    assert translate("unknown.code", "en") == "unknown.code"


class Payload(BaseModel):
    n: int


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError()

    @app.get("/quota")
    async def quota() -> None:
        raise QuotaExceededError("quota.projects_exceeded", limit=3)

    @app.get("/stale")
    async def stale() -> None:
        raise StaleDataError("x")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    @app.post("/validate")
    async def validate(body: Payload) -> Payload:
        return body

    return app


async def _client() -> AsyncClient:
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://t")


async def test_domain_error_is_problem_details_in_portuguese_by_default() -> None:
    async with await _client() as c:
        r = await c.get("/missing", headers={"X-Request-ID": "abc123"})
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["code"] == "error.not_found"
    assert body["status"] == 404
    assert body["instance"] == "/missing"
    assert body["request_id"] == "abc123"
    assert body["title"].startswith("O item")
    assert r.headers["X-Request-ID"] == "abc123"


async def test_domain_error_in_english_with_params() -> None:
    async with await _client() as c:
        r = await c.get("/quota", headers={"Accept-Language": "en"})
    assert r.status_code == 403
    assert "limit of 3 projects" in r.json()["title"]


async def test_optimistic_lock_conflict_becomes_409() -> None:
    async with await _client() as c:
        r = await c.get("/stale")
    assert r.status_code == 409
    assert r.json()["code"] == "error.version_conflict"


async def test_validation_error_lists_fields() -> None:
    async with await _client() as c:
        r = await c.post("/validate", json={"n": "not a number"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "error.validation"
    assert body["errors"][0]["loc"] == ["body", "n"]


async def test_unexpected_error_hides_details() -> None:
    async with await _client() as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    assert "unexpected" not in r.text
    assert r.json()["code"] == "error.internal"


async def test_unknown_route_is_problem_details() -> None:
    async with await _client() as c:
        r = await c.get("/nope")
    assert r.status_code == 404
    assert r.json()["code"] == "error.not_found"
