from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class RunConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class ApiV1Prefix(BaseModel):
    prefix: str = "/v1"


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: ApiV1Prefix = ApiV1Prefix()


class DataBaseConfig(BaseModel):
    host: str
    port: int
    user: str
    password: str
    name: str
    provider: str = "postgresql+psycopg_async"

    @property
    def dsn(self) -> str:
        return f"{self.provider}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    echo_pool: bool = False
    max_overflow: int = 10
    pool_size: int = 50


class Settings(BaseSettings):
    debug: bool
    base_url: str
    base_dir: Path = BASE_DIR  # ..\fastapi-starter

    db: DataBaseConfig
    cors_origins: list[str]
    run: RunConfig = RunConfig()
    api: ApiPrefix = ApiPrefix()

    model_config = SettingsConfigDict(
        env_file=(base_dir / ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )


def get_settings():
    return Settings()


settings = get_settings()
