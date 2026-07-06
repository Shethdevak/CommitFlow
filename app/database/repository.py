from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import delete
from app.database.models import AICache, FeedbackLog

class DatabaseRepository:
    """Manages transactional interactions with SQLite databases for cache and feedback."""

    def __init__(self, session: Session):
        self.session = session

    def get_cached_prediction(self, commit_hash: str, repository: str) -> Optional[AICache]:
        """Retrieves a cached prediction entry for a given commit hash and repository."""
        return self.session.query(AICache).filter(
            AICache.commit_hash == commit_hash,
            AICache.repository == repository
        ).first()

    def save_cache_entry(
        self,
        commit_hash: str,
        repository: str,
        predicted_feature: str,
        confidence: int,
        reason: str,
        provider: str
    ) -> AICache:
        """Saves or updates a cache entry for a prediction."""
        existing = self.get_cached_prediction(commit_hash, repository)
        if existing:
            existing.predicted_feature = predicted_feature
            existing.confidence = confidence
            existing.reason = reason
            existing.provider = provider
            existing.created_at = datetime.utcnow()
            cache_entry = existing
        else:
            cache_entry = AICache(
                commit_hash=commit_hash,
                repository=repository,
                predicted_feature=predicted_feature,
                confidence=confidence,
                reason=reason,
                provider=provider
            )
            self.session.add(cache_entry)
        self.session.flush()
        return cache_entry

    def get_all_cache_entries(self) -> List[AICache]:
        """Retrieves all entries currently saved in the cache."""
        return self.session.query(AICache).order_by(AICache.created_at.desc()).all()

    def clear_cache(self) -> int:
        """Deletes all cache entries and returns the count of deleted items."""
        result = self.session.execute(delete(AICache))
        return result.rowcount

    def add_feedback(
        self,
        commit_hash: str,
        repository: str,
        commit_message: str,
        predicted_feature: str,
        corrected_feature: str
    ) -> FeedbackLog:
        """Stores a manual correction to standardise AI classifications in the future."""
        existing = self.session.query(FeedbackLog).filter(
            FeedbackLog.commit_hash == commit_hash,
            FeedbackLog.repository == repository
        ).first()

        if existing:
            existing.corrected_feature = corrected_feature
            existing.predicted_feature = predicted_feature
            existing.corrected_at = datetime.utcnow()
            feedback_log = existing
        else:
            feedback_log = FeedbackLog(
                commit_hash=commit_hash,
                repository=repository,
                commit_message=commit_message,
                predicted_feature=predicted_feature,
                corrected_feature=corrected_feature
            )
            self.session.add(feedback_log)
        self.session.flush()
        return feedback_log

    def get_feedback_logs(self, limit: int = 15) -> List[FeedbackLog]:
        """Retrieves user feedback corrections to build few-shot prompts."""
        return self.session.query(FeedbackLog).order_by(FeedbackLog.corrected_at.desc()).limit(limit).all()
