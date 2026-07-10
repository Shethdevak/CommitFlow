import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Git Configuration
    github_token: Optional[str] = Field(None, validation_alias="GITHUB_TOKEN")
    gitlab_token: Optional[str] = Field(None, validation_alias="GITLAB_TOKEN")
    gitlab_api_url: str = Field("https://gitlab.com", validation_alias="GITLAB_API_URL")
    author_name: Optional[str] = Field(None, validation_alias="AUTHOR_NAME")

    # Redmine Configuration
    redmine_url: str = Field(..., validation_alias="REDMINE_URL")
    redmine_api_key: str = Field(..., validation_alias="REDMINE_API_KEY")

    # Database & Mappings
    db_path: str = Field("commitflow.db", validation_alias="DB_PATH")
    mappings_path: str = Field("configs/repo_mappings.yaml", validation_alias="MAPPINGS_PATH")

    # Localization
    timezone: str = Field("UTC", validation_alias="TIMEZONE")

    # Daily worklog goals
    daily_hour_goal: float = Field(8.0, validation_alias="DAILY_HOUR_GOAL")
    min_todos: int = Field(3, validation_alias="MIN_TODOS")
    project_match_threshold: int = Field(70, validation_alias="PROJECT_MATCH_THRESHOLD")

    # AI Configurations
    ai_provider: str = Field("openai", validation_alias="AI_PROVIDER")
    ai_confidence_threshold: int = Field(80, validation_alias="AI_CONFIDENCE_THRESHOLD")
    default_feature: str = Field("General Development", validation_alias="DEFAULT_FEATURE")

    # OpenAI
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", validation_alias="OPENAI_MODEL")

    # Gemini
    gemini_api_key: Optional[str] = Field(None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-1.5-flash", validation_alias="GEMINI_MODEL")

    # Anthropic
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-3-5-sonnet-20240620", validation_alias="ANTHROPIC_MODEL")

    # OpenRouter
    openrouter_api_key: Optional[str] = Field(None, validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field("meta-llama/llama-3.1-70b-instruct", validation_alias="OPENROUTER_MODEL")

    # Ollama
    ollama_api_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_API_URL")
    ollama_model: str = Field("llama3", validation_alias="OLLAMA_MODEL")

    # Groq
    groq_api_key: Optional[str] = Field(None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field("llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")

    @field_validator("ai_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = ["openai", "gemini", "anthropic", "openrouter", "ollama", "groq"]
        val = v.lower().strip()
        if val not in allowed:
            raise ValueError(f"AI_PROVIDER must be one of {allowed}")
        return val

    @field_validator("redmine_url")
    @classmethod
    def validate_redmine_url(cls, v: str) -> str:
        return v.rstrip("/")

def load_settings() -> Settings:
    """Helper to load and validate environment settings."""
    return Settings()
