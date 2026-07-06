from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from app.database.connection import Base

class AICache(Base):
    """Stores AI classification decisions for commits to avoid re-evaluating them."""
    __tablename__ = "ai_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commit_hash = Column(String(64), index=True, nullable=False)
    repository = Column(String(255), nullable=False)
    predicted_feature = Column(String(255), nullable=False)
    confidence = Column(Integer, nullable=False)
    reason = Column(Text, nullable=True)
    provider = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("commit_hash", "repository", name="uq_commit_repo"),
    )

class FeedbackLog(Base):
    """Stores corrected feature mapping from user feedback for few-shot prompt training."""
    __tablename__ = "feedback_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commit_hash = Column(String(64), nullable=False)
    repository = Column(String(255), nullable=False)
    commit_message = Column(Text, nullable=False)
    predicted_feature = Column(String(255), nullable=False)
    corrected_feature = Column(String(255), nullable=False)
    corrected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("commit_hash", "repository", name="uq_feedback_commit_repo"),
    )
