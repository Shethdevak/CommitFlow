"""Convert stored UserSettings ↔ Settings mapping for SyncService."""

import os
from typing import Any, Dict, Optional
from api.db.models import UserSettings
from api.security import encrypt_text, decrypt_text, mask_secret
from api.schemas import UserSettingsUpdate, UserSettingsOut


SECRET_FIELDS = {
    "github_token": "github_token_enc",
    "gitlab_token": "gitlab_token_enc",
    "redmine_api_key": "redmine_api_key_enc",
    "openai_api_key": "openai_api_key_enc",
    "gemini_api_key": "gemini_api_key_enc",
    "anthropic_api_key": "anthropic_api_key_enc",
    "openrouter_api_key": "openrouter_api_key_enc",
    "groq_api_key": "groq_api_key_enc",
}


def apply_settings_update(row: UserSettings, payload: UserSettingsUpdate) -> UserSettings:
    data = payload.model_dump(exclude_unset=True)
    for field, enc_col in SECRET_FIELDS.items():
        if field in data:
            value = data.pop(field)
            if value is not None and str(value).strip() != "":
                setattr(row, enc_col, encrypt_text(str(value).strip()))

    plain_map = {
        "author_name": "author_name",
        "timezone": "timezone",
        "gitlab_api_url": "gitlab_api_url",
        "redmine_url": "redmine_url",
        "ai_provider": "ai_provider",
        "openai_model": "openai_model",
        "gemini_model": "gemini_model",
        "anthropic_model": "anthropic_model",
        "openrouter_model": "openrouter_model",
        "ollama_api_url": "ollama_api_url",
        "ollama_model": "ollama_model",
        "groq_model": "groq_model",
        "mappings_yaml": "mappings_yaml",
    }
    for src, dest in plain_map.items():
        if src in data and data[src] is not None:
            setattr(row, dest, data[src])

    if "daily_hour_goal" in data and data["daily_hour_goal"] is not None:
        row.daily_hour_goal = str(data["daily_hour_goal"])
    if "min_todos" in data and data["min_todos"] is not None:
        row.min_todos = str(data["min_todos"])
    if "project_match_threshold" in data and data["project_match_threshold"] is not None:
        row.project_match_threshold = str(data["project_match_threshold"])

    return row


def settings_to_public(row: Optional[UserSettings]) -> UserSettingsOut:
    if not row:
        return UserSettingsOut()

    def _dec(enc: Optional[str]) -> Optional[str]:
        if not enc:
            return None
        try:
            return decrypt_text(enc)
        except Exception:
            return None

    gh = _dec(row.github_token_enc)
    gl = _dec(row.gitlab_token_enc)
    rm = _dec(row.redmine_api_key_enc)
    groq = _dec(row.groq_api_key_enc)
    oai = _dec(row.openai_api_key_enc)
    gem = _dec(row.gemini_api_key_enc)
    ant = _dec(row.anthropic_api_key_enc)
    oro = _dec(row.openrouter_api_key_enc)

    return UserSettingsOut(
        author_name=row.author_name,
        timezone=row.timezone,
        gitlab_api_url=row.gitlab_api_url,
        redmine_url=row.redmine_url,
        ai_provider=row.ai_provider,
        daily_hour_goal=float(row.daily_hour_goal) if row.daily_hour_goal else 8.0,
        min_todos=int(row.min_todos) if row.min_todos else 3,
        project_match_threshold=int(row.project_match_threshold) if row.project_match_threshold else 70,
        openai_model=row.openai_model,
        gemini_model=row.gemini_model,
        anthropic_model=row.anthropic_model,
        openrouter_model=row.openrouter_model,
        ollama_api_url=row.ollama_api_url,
        ollama_model=row.ollama_model,
        groq_model=row.groq_model,
        mappings_yaml=row.mappings_yaml,
        github_token=mask_secret(gh),
        gitlab_token=mask_secret(gl),
        redmine_api_key=mask_secret(rm),
        groq_api_key=mask_secret(groq),
        openai_api_key=mask_secret(oai),
        gemini_api_key=mask_secret(gem),
        anthropic_api_key=mask_secret(ant),
        openrouter_api_key=mask_secret(oro),
        has_github_token=bool(gh),
        has_gitlab_token=bool(gl),
        has_redmine_api_key=bool(rm),
        has_groq_api_key=bool(groq),
        has_openai_api_key=bool(oai),
    )


def build_settings_mapping(row: UserSettings, *, db_path: str, mappings_path: str) -> Dict[str, Any]:
    """Produce kwargs accepted by app.config.settings.Settings.from_mapping."""

    def _req_dec(enc: Optional[str], label: str) -> str:
        if not enc:
            raise ValueError(f"Missing required setting: {label}")
        return decrypt_text(enc)

    def _opt_dec(enc: Optional[str]) -> Optional[str]:
        return decrypt_text(enc) if enc else None

    if not row.redmine_url:
        raise ValueError("REDMINE_URL is required in settings")

    return {
        "GITHUB_TOKEN": _opt_dec(row.github_token_enc),
        "GITLAB_TOKEN": _opt_dec(row.gitlab_token_enc),
        "GITLAB_API_URL": row.gitlab_api_url or "https://gitlab.com",
        "AUTHOR_NAME": row.author_name,
        "REDMINE_URL": row.redmine_url,
        "REDMINE_API_KEY": _req_dec(row.redmine_api_key_enc, "REDMINE_API_KEY"),
        "DB_PATH": db_path,
        "MAPPINGS_PATH": mappings_path,
        "TIMEZONE": row.timezone or "UTC",
        "DAILY_HOUR_GOAL": float(row.daily_hour_goal or 8),
        "MIN_TODOS": int(row.min_todos or 3),
        "PROJECT_MATCH_THRESHOLD": int(row.project_match_threshold or 70),
        "AI_PROVIDER": (row.ai_provider or "groq").lower(),
        "OPENAI_API_KEY": _opt_dec(row.openai_api_key_enc),
        "OPENAI_MODEL": row.openai_model or "gpt-4o",
        "GEMINI_API_KEY": _opt_dec(row.gemini_api_key_enc),
        "GEMINI_MODEL": row.gemini_model or "gemini-1.5-flash",
        "ANTHROPIC_API_KEY": _opt_dec(row.anthropic_api_key_enc),
        "ANTHROPIC_MODEL": row.anthropic_model or "claude-3-5-sonnet-20240620",
        "OPENROUTER_API_KEY": _opt_dec(row.openrouter_api_key_enc),
        "OPENROUTER_MODEL": row.openrouter_model or "meta-llama/llama-3.1-70b-instruct",
        "OLLAMA_API_URL": row.ollama_api_url or "http://localhost:11434",
        "OLLAMA_MODEL": row.ollama_model or "llama3",
        "GROQ_API_KEY": _opt_dec(row.groq_api_key_enc),
        "GROQ_MODEL": row.groq_model or "llama-3.3-70b-versatile",
    }


def ensure_user_paths(user_id: int, user_data_dir: str, mappings_yaml: Optional[str]) -> tuple[str, str]:
    """Create per-user DB + mappings files; return (db_path, mappings_path)."""
    user_dir = os.path.join(user_data_dir, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    db_path = os.path.join(user_dir, "commitflow.db")
    mappings_path = os.path.join(user_dir, "repo_mappings.yaml")

    if mappings_yaml and mappings_yaml.strip():
        with open(mappings_path, "w", encoding="utf-8") as f:
            f.write(mappings_yaml)
    elif not os.path.exists(mappings_path):
        # Fall back to project default mappings
        default = "configs/repo_mappings.yaml"
        if os.path.exists(default):
            with open(default, "r", encoding="utf-8") as src, open(mappings_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        else:
            with open(mappings_path, "w", encoding="utf-8") as f:
                f.write("repositories: {}\n")

    return db_path, mappings_path
