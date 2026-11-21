from functools import lru_cache
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Require an explicit deployment mode so a missing production variable
    # cannot silently disable production-only security validation.
    app_env: Literal["development", "test", "production"]
    api_v1_prefix: str = "/api/v1"
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "smart_exam_ethiopia"
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    frontend_origin: str = "http://localhost:3000"
    admin_bootstrap_token: str | None = Field(default=None, min_length=32)

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.app_env.lower() == "production":
            if "replace-with" in self.jwt_secret_key.lower():
                raise ValueError("Set a unique production JWT_SECRET_KEY.")
            if not self.frontend_origin.startswith("https://"):
                raise ValueError("Production FRONTEND_ORIGIN must use HTTPS.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
