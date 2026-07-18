"""Web API configuration (server-side only — does not replace user CLI .env)."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # App
    api_secret_key: str = Field("change-me-in-production-use-long-random-string", validation_alias="API_SECRET_KEY")
    api_fernet_key: Optional[str] = Field(None, validation_alias="API_FERNET_KEY")
    api_cors_origins: str = Field("http://localhost:5173,http://127.0.0.1:5173", validation_alias="API_CORS_ORIGINS")
    api_database_url: str = Field("sqlite:///./data/commitflow_web.db", validation_alias="API_DATABASE_URL")
    api_user_data_dir: str = Field("data/users", validation_alias="API_USER_DATA_DIR")
    api_frontend_url: str = Field("http://localhost:5173", validation_alias="API_FRONTEND_URL")
    api_public_url: str = Field("http://localhost:8000", validation_alias="API_PUBLIC_URL")
    jwt_expire_hours: int = Field(72, validation_alias="JWT_EXPIRE_HOURS")

    # GitHub OAuth (login with GitHub — optional)
    github_oauth_client_id: Optional[str] = Field(None, validation_alias="GITHUB_OAUTH_CLIENT_ID")
    github_oauth_client_secret: Optional[str] = Field(None, validation_alias="GITHUB_OAUTH_CLIENT_SECRET")


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
