from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    app_name: str = "방자취 API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./bangjach.db"
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
    review_photo_local_dir: str = ".uploads/review-photos"

    @model_validator(mode="after")
    def production(self):
        if self.environment == "production":
            if len(self.jwt_secret) < 32:
                raise ValueError("Production requires JWT_SECRET with at least 32 characters")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("Production requires PostgreSQL")
        return self


settings = Settings()
