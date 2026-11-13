import pytest

from app.core.config import Settings


def test_comma_separated_lists_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost, abc.trycloudflare.com,")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080,https://abc.trycloudflare.com")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.allowed_hosts == ["localhost", "abc.trycloudflare.com"]
    assert settings.cors_origins == ["http://localhost:8080", "https://abc.trycloudflare.com"]


def test_database_url_is_built_from_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss")
    url = Settings(_env_file=None).database_url  # type: ignore[call-arg]
    assert url.startswith("postgresql+asyncpg://")
    assert "@db:5432/" in url
    assert "p%40ss" in url
