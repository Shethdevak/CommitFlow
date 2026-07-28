import json
from typing import List, Dict
from loguru import logger
from app.ai.provider import AIProvider
from app.models.domain import Commit, RedmineFeature, AIClassificationResult, FeatureMappingSelection
from app.database.models import FeedbackLog
from app.services.feature_match import resolve_related_feature


class FeatureClassifierService:
    """Uses AI to classify developer commits into Redmine Features, applying corrections and similarity matching."""

    def __init__(
        self,
        ai_provider: AIProvider,
        confidence_threshold: int = 80,
        default_feature: str = "General Development",
    ):
        self.ai_provider = ai_provider
        self.confidence_threshold = confidence_threshold
        self.default_feature = default_feature

    def build_prompt(
        self,
        repository: str,
        project_name: str,
        commits: List[Commit],
        features: List[RedmineFeature],
        feedback_logs: List[FeedbackLog],
    ) -> str:
        """Constructs a few-shot prompt for classification, incorporating past corrections."""
        features_list_str = "\n".join(
            [
                f"- '{f.subject}' (ID: {f.id})"
                + (f": {f.description}" if f.description else "")
                for f in features
            ]
        )

        commits_list_str = ""
        for idx, c in enumerate(commits):
            commits_list_str += (
                f"\nCommit #{idx+1}:\n"
                f"  Hash: {c.hash}\n"
                f"  Subject: {c.message}\n"
                f"  Description: {c.description}\n"
                f"  Changed Files:\n"
            )
            for f in c.changed_files:
                commits_list_str += f"    - {f}\n"
            commits_list_str += f"  Stats: +{c.additions}, -{c.deletions}\n"

        feedback_context = ""
        if feedback_logs:
            feedback_context = "\n=== HISTORICAL CORRECTIONS (LEARNING SYSTEM) ===\n"
            feedback_context += "Use the following previous corrections as rules for your classifications:\n"
            for log in feedback_logs:
                feedback_context += (
                    f"- Repository: '{log.repository}'\n"
                    f"  Commit: '{log.commit_message}'\n"
                    f"  Initially predicted: '{log.predicted_feature}'\n"
                    f"  Corrected feature: '{log.corrected_feature}' "
                    f"(IMPORTANT: Always classify similar commits into this feature!)\n"
                )
            feedback_context += "================================================\n"

        prompt = f"""
You are an AI assistant designed to help developers log their work automatically.
Your task is to classify today's Git commits into the correct Redmine Feature (Parent Issue).

CONTEXT:
Repository: {repository}
Redmine Project: {project_name}

AVAILABLE REDMINE FEATURES (choose from these parent issues):
{features_list_str}
- '{self.default_feature}' (last resort only)

{feedback_context}

COMMITS TO CLASSIFY:
{commits_list_str}

INSTRUCTIONS:
1. Match each commit to the MOST RELATED available Redmine feature — not only exact title matches.
   Use commit subject, description, and file paths (e.g. orders/, dashboard/, onboarding/, payment/).
2. Prefer a related existing feature over '{self.default_feature}' whenever there is a reasonable link
   (same product area, module, or domain words in paths/messages).
3. Return the feature's exact subject string in 'feature_name' when it is one of the available features.
4. Assign confidence 0–100. Medium confidence (50–79) is OK when the feature is clearly related.
5. Use '{self.default_feature}' ONLY when no available feature is even loosely related
   (true housekeeping with no domain signal).
6. Give a short 'reason' citing files or keywords that guided the choice.
7. You may group multiple commits under the same feature.

OUTPUT FORMAT:
Respond with valid JSON only (no markdown fences):
{{
    "selected_features": [
        {{
            "feature_name": "Exact or closest Redmine Feature subject",
            "confidence": 95,
            "commits": ["hash1", "hash2"],
            "reason": "Because modified files under orders/ and message mentions expired status."
        }}
    ]
}}
"""
        return prompt.strip()

    def classify_commits(
        self,
        repository: str,
        project_name: str,
        commits: List[Commit],
        features: List[RedmineFeature],
        feedback_logs: List[FeedbackLog],
    ) -> AIClassificationResult:
        """Invokes the AI provider and resolves predictions onto related Redmine features."""
        if not commits:
            return AIClassificationResult(selected_features=[])

        commits_by_hash: Dict[str, Commit] = {c.hash: c for c in commits}
        prompt = self.build_prompt(repository, project_name, commits, features, feedback_logs)

        try:
            raw_response = self.ai_provider.classify(prompt)
            cleaned_response = raw_response.strip()
            if cleaned_response.startswith("```"):
                lines = cleaned_response.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_response = "\n".join(lines).strip()

            data = json.loads(cleaned_response)
            parsed = AIClassificationResult(**data)

            resolved_selections: List[FeatureMappingSelection] = []

            for selection in parsed.selected_features:
                predicted_name = (selection.feature_name or "").strip()
                selection_commits = [
                    commits_by_hash[h] for h in selection.commits if h in commits_by_hash
                ]
                if not selection_commits:
                    selection_commits = commits

                resolved_name = resolve_related_feature(
                    predicted_name=predicted_name,
                    commits=selection_commits,
                    features=features,
                    default_feature=self.default_feature,
                    confidence=int(selection.confidence or 0),
                    confidence_threshold=int(self.confidence_threshold),
                )

                resolved_selections.append(
                    FeatureMappingSelection(
                        feature_name=resolved_name,
                        confidence=selection.confidence,
                        commits=selection.commits,
                        reason=selection.reason,
                    )
                )

            return AIClassificationResult(selected_features=resolved_selections)

        except Exception as e:
            logger.error(
                f"AI classification failed or returned invalid output: {e}. "
                "Trying content-based feature match before default."
            )
            related = resolve_related_feature(
                predicted_name=self.default_feature,
                commits=commits,
                features=features,
                default_feature=self.default_feature,
                confidence=0,
                confidence_threshold=self.confidence_threshold,
            )
            all_hashes = [c.hash for c in commits]
            return AIClassificationResult(
                selected_features=[
                    FeatureMappingSelection(
                        feature_name=related,
                        confidence=0,
                        commits=all_hashes,
                        reason=f"Fallback after AI error: {e}",
                    )
                ]
            )
