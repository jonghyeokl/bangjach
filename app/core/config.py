from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8")
    app_name: str = "방자취 API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/bangjach.db"
    cors_origins: list[str] = ["http://localhost:8081", "http://127.0.0.1:8081"]
    jwt_secret: str = ""
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=30, ge=1)
    admin_user_ids: list[str] = []
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=10, gt=0, le=60)
    rate_limit_enabled: bool = True
    review_photo_bucket: str = ""
    review_photo_local_dir: str = "data/photos"

    @model_validator(mode="after")
    def local_paths(self):
        url = make_url(self.database_url)
        if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
            path = Path(url.database)
            if not path.is_absolute():
                self.database_url = url.set(database=str(ROOT / path)).render_as_string(
                    hide_password=False
                )
        photos = Path(self.review_photo_local_dir)
        if not photos.is_absolute():
            self.review_photo_local_dir = str(ROOT / photos)
        return self

    @model_validator(mode="after")
    def production(self):
        if self.environment == "production":
            if len(self.jwt_secret) < 32:
                raise ValueError("Production requires JWT_SECRET with at least 32 characters")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("Production requires PostgreSQL")
        return self


settings = Settings()
