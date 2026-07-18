from typing import Optional
import re
from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_RULE = (
    "Password must be at least 8 characters and include 1 uppercase letter, "
    "1 number, and 1 special character"
)


def validate_strong_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError(PASSWORD_RULE)
    if not re.search(r"[A-Z]", password):
        raise ValueError(PASSWORD_RULE)
    if not re.search(r"[0-9]", password):
        raise ValueError(PASSWORD_RULE)
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError(PASSWORD_RULE)
    return password


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        return validate_strong_password(value)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Login/register response — JWT is set as an HttpOnly cookie, not returned in JSON."""

    user: "UserOut"


class TokenResponse(BaseModel):
    """Deprecated shape kept for compatibility with older clients."""

    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: Optional[str] = None
    display_name: Optional[str] = None
    github_login: Optional[str] = None

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    # Prefer sending full values; secrets left blank/null keep existing stored value
    author_name: Optional[str] = None
    timezone: Optional[str] = None
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    gitlab_api_url: Optional[str] = None
    redmine_url: Optional[str] = None
    redmine_api_key: Optional[str] = None
    ai_provider: Optional[str] = None
    daily_hour_goal: Optional[float] = None
    min_todos: Optional[int] = None
    project_match_threshold: Optional[int] = None
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    openrouter_model: Optional[str] = None
    ollama_api_url: Optional[str] = None
    ollama_model: Optional[str] = None
    groq_model: Optional[str] = None
    mappings_yaml: Optional[str] = None


class UserSettingsOut(BaseModel):
    author_name: Optional[str] = None
    timezone: Optional[str] = None
    gitlab_api_url: Optional[str] = None
    redmine_url: Optional[str] = None
    ai_provider: Optional[str] = None
    daily_hour_goal: Optional[float] = None
    min_todos: Optional[int] = None
    project_match_threshold: Optional[int] = None
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    openrouter_model: Optional[str] = None
    ollama_api_url: Optional[str] = None
    ollama_model: Optional[str] = None
    groq_model: Optional[str] = None
    mappings_yaml: Optional[str] = None
    # Masked secrets
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    redmine_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    has_github_token: bool = False
    has_gitlab_token: bool = False
    has_redmine_api_key: bool = False
    has_groq_api_key: bool = False
    has_openai_api_key: bool = False


class SyncRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD; default today in user timezone
    dry_run: bool = True
    today: bool = True


class PlannedTodoOut(BaseModel):
    subject: str
    hours: float
    project_name: str
    feature_name: str
    is_synthetic: bool
    project_id: int = 0
    parent_issue_id: Optional[int] = None
    description: str = ""


class CommitPlannedRequest(BaseModel):
    """Write a prior dry-run plan to Redmine without re-fetching commits."""
    date: str
    planned_todos: list[PlannedTodoOut]


class SyncResultOut(BaseModel):
    date: str
    dry_run: bool
    processed_commits_count: int
    cached_commits_count: int
    todos_planned: int
    hours_logged: float
    created_issues: list[int]
    updated_issues: list[int]
    time_entries_created: int
    errors: list[str]
    unmapped_repos: list[str]
    planned_todos: list[PlannedTodoOut]


TokenResponse.model_rebuild()
AuthResponse.model_rebuild()
