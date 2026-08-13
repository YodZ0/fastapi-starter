"""
Application settings.
"""

from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BASE_DIR = Path(__file__).resolve().parent.parent  # fastapi-starter


class ApplicationConfig(BaseModel):
    title: str
    docs_url: str | None = None
    redoc_url: str | None = None
    openapi_url: str | None = None


class RunConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class APIConfigV1(BaseModel):
    prefix: str = "/v1"


class APIConfig(BaseModel):
    prefix: str = "/api"
    v1: APIConfigV1 = APIConfigV1()


class DatabaseConfig(BaseModel):
    host: str
    port: int
    user: str
    password: SecretStr
    name: str
    provider: str = "postgresql+asyncpg"

    echo: bool = False
    echo_pool: bool = False

    # Pool sizing is per worker process: N workers hold up to
    # N * (pool_size + max_overflow) connections, and that total has to stay
    # under the server's max_connections (100 by default in Postgres).
    pool_size: int = 10
    max_overflow: int = 5
    pool_timeout: float = 30.0
    # Recycle below any idle timeout enforced by the server or a proxy
    # (pgbouncer, cloud load balancers), so the pool never hands out a socket
    # the other side has already dropped.
    pool_recycle: int = 1800
    pool_pre_ping: bool = True

    statement_timeout_ms: int = 10_000

    @property
    def url(self) -> URL:
        """
        SQLAlchemy connection URL.

        Built via URL.create() rather than f-string concatenation: it
        percent-encodes the credentials, so a password containing "@", "/", "#"
        or ":" no longer corrupts the URL. Note that repr() of the result hides
        the password, unlike the raw string.
        """
        return URL.create(
            drivername=self.provider,
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.name,
        )

    @property
    def dsn(self) -> str:
        """
        Connection URL rendered as a string, password included.

        Only for the few consumers that cannot take a URL object (Alembic
        offline mode). Prefer `url`, which keeps the password out of reprs.
        """
        return self.url.render_as_string(hide_password=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_file=(BASE_DIR / ".env"),
        extra="ignore",
    )
    debug: bool = False
    base_dir: Path = BASE_DIR
    cors_origins: list[str]

    app: ApplicationConfig
    run: RunConfig = RunConfig()
    api: APIConfig = APIConfig()
    db: DatabaseConfig


settings = Settings()
