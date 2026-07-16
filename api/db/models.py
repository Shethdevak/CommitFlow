"""SQLAlchemy models for the web multi-user database."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    github_id = Column(String(64), unique=True, nullable=True, index=True)
    github_login = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Non-secret preferences
    author_name = Column(String(255), nullable=True)
    timezone = Column(String(64), default="Asia/Kolkata")
    gitlab_api_url = Column(String(512), default="https://gitlab.com")
    redmine_url = Column(String(512), nullable=True)
    ai_provider = Column(String(32), default="groq")
    daily_hour_goal = Column(String(16), default="8")
    min_todos = Column(String(16), default="3")
    project_match_threshold = Column(String(16), default="70")
    openai_model = Column(String(128), nullable=True)
    gemini_model = Column(String(128), nullable=True)
    anthropic_model = Column(String(128), nullable=True)
    openrouter_model = Column(String(128), nullable=True)
    ollama_api_url = Column(String(512), nullable=True)
    ollama_model = Column(String(128), nullable=True)
    groq_model = Column(String(128), nullable=True)
    mappings_yaml = Column(Text, nullable=True)  # optional per-user overrides YAML

    # Encrypted secrets (Fernet ciphertext)
    github_token_enc = Column(Text, nullable=True)
    gitlab_token_enc = Column(Text, nullable=True)
    redmine_api_key_enc = Column(Text, nullable=True)
    openai_api_key_enc = Column(Text, nullable=True)
    gemini_api_key_enc = Column(Text, nullable=True)
    anthropic_api_key_enc = Column(Text, nullable=True)
    openrouter_api_key_enc = Column(Text, nullable=True)
    groq_api_key_enc = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="settings")
