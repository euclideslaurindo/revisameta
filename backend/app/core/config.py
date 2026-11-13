from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Accept "a,b,c" from the environment as well as a real list."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    """Application settings, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_base_url: str = "http://localhost:8080"
    allowed_hosts: CsvList = Field(default=["localhost", "127.0.0.1"])
    cors_origins: CsvList = Field(default=["http://localhost:8080"])

    jwt_secret: str = "change-me"  # noqa: S105 - overridden by env; checked at startup
    access_token_ttl_minutes: int = 10
    refresh_token_ttl_days: int = 14
    cookie_secure: bool = False

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "revisameta"
    postgres_user: str = "revisameta"
    postgres_password: str = "change-me"  # noqa: S105

    redis_url: str = "redis://redis:6379/0"

    s3_endpoint: str = "http://storage:9000"
    s3_public_endpoint: str = "http://localhost:8080"
    s3_access_key: str = "revisameta"
    s3_secret_key: str = "change-me"  # noqa: S105
    s3_bucket: str = "revisameta-files"
    s3_region: str = "us-east-1"
    upload_session_ttl_hours: int = 24
    pdf_max_size_mb: int = 100
    upload_part_size_mb: int = 10

    stats_r_url: str = "http://stats-r:8000"
    stats_r_timeout_seconds: float = 60.0

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "RevisaMeta <no-reply@revisameta.local>"
    smtp_tls: bool = False

    turnstile_enabled: bool = False
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    quota_projects_per_user: int = 5
    quota_storage_mb_per_user: int = 2048

    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
