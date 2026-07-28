"""Fuzzy matching of commits / AI labels onto real Redmine parent features."""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from loguru import logger
from rapidfuzz import fuzz, process, utils as fuzz_utils

from app.models.domain import Commit, RedmineFeature

# Name-to-feature (AI label → Redmine subject)
NAME_MATCH_MIN = 62
# Commit message/files → feature subject/description (relatedness)
CONTENT_MATCH_MIN = 52


def _feature_label(feature: RedmineFeature) -> str:
    desc = (feature.description or "").strip()
    if desc:
        return f"{feature.subject} {desc[:180]}"
    return feature.subject


def match_feature_by_name(
    name: str,
    features: List[RedmineFeature],
    *,
    min_score: float = NAME_MATCH_MIN,
) -> Optional[Tuple[RedmineFeature, float]]:
    """Best Redmine feature for an AI/cache feature name (typos & near-matches OK)."""
    query = (name or "").strip()
    if not query or not features:
        return None

    by_subject = {f.subject: f for f in features}
    match = process.extractOne(
        query,
        list(by_subject.keys()),
        processor=fuzz_utils.default_process,
        scorer=fuzz.WRatio,
    )
    if match and match[1] >= min_score:
        return by_subject[match[0]], float(match[1])
    return None


def score_commit_against_feature(commit: Commit, feature: RedmineFeature) -> float:
    """How related a commit is to a parent feature (message + paths + description)."""
    subject = feature.subject or ""
    label = _feature_label(feature)
    message = f"{commit.message or ''} {commit.description or ''}".strip()
    scores = [
        fuzz.WRatio(message, subject, processor=fuzz_utils.default_process),
        fuzz.partial_ratio(message, subject, processor=fuzz_utils.default_process),
        fuzz.token_set_ratio(message, label, processor=fuzz_utils.default_process),
    ]
    for path in (commit.changed_files or [])[:40]:
        scores.append(
            fuzz.partial_ratio(path, subject, processor=fuzz_utils.default_process)
        )
        # Folder/module hints: orders/, dashboard/, onboarding/
        scores.append(
            fuzz.token_set_ratio(path.replace("/", " "), subject, processor=fuzz_utils.default_process)
        )
    return float(max(scores) if scores else 0.0)


def best_feature_for_commits(
    commits: Iterable[Commit],
    features: List[RedmineFeature],
    *,
    min_score: float = CONTENT_MATCH_MIN,
) -> Optional[Tuple[RedmineFeature, float]]:
    """Pick the most related real parent feature for one or more commits."""
    commit_list = list(commits)
    if not commit_list or not features:
        return None

    best: Optional[Tuple[RedmineFeature, float]] = None
    for feature in features:
        score = max(score_commit_against_feature(c, feature) for c in commit_list)
        if best is None or score > best[1]:
            best = (feature, score)

    if best and best[1] >= min_score:
        logger.info(
            f"Related feature match: '{best[0].subject}' "
            f"(score {best[1]:.1f}) for {len(commit_list)} commit(s)"
        )
        return best

    if best:
        logger.debug(
            f"Best related feature '{best[0].subject}' scored {best[1]:.1f} "
            f"< threshold {min_score}; skipping"
        )
    return None


def resolve_related_feature(
    *,
    predicted_name: str,
    commits: List[Commit],
    features: List[RedmineFeature],
    default_feature: str,
    confidence: int,
    confidence_threshold: int,
) -> str:
    """
    Resolve to a real Redmine feature subject when possible.

    Order:
    1. Fuzzy match AI name onto real features
    2. If confidence is low or name miss — content match from commit message/files
    3. Default feature name only as last resort (may not exist in Redmine yet)
    """
    predicted = (predicted_name or "").strip()

    # 1) Prefer a real feature close to the AI label (even when confidence is modest)
    name_hit = match_feature_by_name(predicted, features)
    if name_hit and (
        confidence >= confidence_threshold or name_hit[1] >= 78
    ):
        feature, score = name_hit
        logger.info(
            f"Resolved AI feature '{predicted}' → '{feature.subject}' "
            f"(name score {score:.1f}, confidence {confidence}%)"
        )
        return feature.subject

    # 2) Relatedness from commit content (handles "orders" → Orders feature, etc.)
    content_hit = best_feature_for_commits(commits, features)
    if content_hit:
        feature, score = content_hit
        logger.info(
            f"Using related feature '{feature.subject}' for prediction "
            f"'{predicted}' (content score {score:.1f}, confidence {confidence}%)"
        )
        return feature.subject

    # 3) Weaker name match still better than inventing a missing default
    if name_hit:
        feature, score = name_hit
        logger.info(
            f"Weak name match '{predicted}' → '{feature.subject}' (score {score:.1f})"
        )
        return feature.subject

    # 4) Default only if it exists as a real feature; else keep predicted / default label
    default_hit = match_feature_by_name(default_feature, features, min_score=90)
    if default_hit:
        logger.info(
            f"No related feature for '{predicted}'; using existing default "
            f"'{default_hit[0].subject}'"
        )
        return default_hit[0].subject

    logger.warning(
        f"No related Redmine feature for '{predicted}' "
        f"(confidence {confidence}%). Keeping '{default_feature}' label."
    )
    return default_feature
