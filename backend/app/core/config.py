from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "smart_exam_ethiopia"
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    frontend_origin: str = "http://localhost:3000"

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.app_env.lower() == "production":
            if "replace-with" in self.jwt_secret_key.lower():
                raise ValueError("Set a unique production JWT_SECRET_KEY.")
            if self.frontend_origin.startswith("http://localhost"):
                raise ValueError("Set FRONTEND_ORIGIN to the deployed HTTPS frontend.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
