import json
from typing import List, Dict, Any, Optional
from loguru import logger
from rapidfuzz import process, utils as fuzz_utils
from app.ai.provider import AIProvider
from app.models.domain import Commit, RedmineFeature, AIClassificationResult, FeatureMappingSelection
from app.database.models import FeedbackLog

class FeatureClassifierService:
    """Uses AI to classify developer commits into Redmine Features, applying corrections and similarity matching."""

    def __init__(self, ai_provider: AIProvider, confidence_threshold: int = 80, default_feature: str = "General Development"):
        self.ai_provider = ai_provider
        self.confidence_threshold = confidence_threshold
        self.default_feature = default_feature

    def build_prompt(
        self,
        repository: str,
        project_name: str,
        commits: List[Commit],
        features: List[RedmineFeature],
        feedback_logs: List[FeedbackLog]
    ) -> str:
        """Constructs a few-shot prompt for classification, incorporating past corrections."""
        features_list_str = "\n".join([
            f"- '{f.subject}' (ID: {f.id})" + (f": {f.description}" if f.description else "")
            for f in features
        ])

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

        # Construct few-shot feedback context
        feedback_context = ""
        if feedback_logs:
            feedback_context = "\n=== HISTORICAL CORRECTIONS (LEARNING SYSTEM) ===\n"
            feedback_context += "Use the following previous corrections as rules for your classifications:\n"
            for log in feedback_logs:
                feedback_context += (
                    f"- Repository: '{log.repository}'\n"
                    f"  Commit: '{log.commit_message}'\n"
                    f"  Initially predicted: '{log.predicted_feature}'\n"
                    f"  Corrected feature: '{log.corrected_feature}' (IMPORTANT: Always classify similar commits into this feature!)\n"
                )
            feedback_context += "================================================\n"

        prompt = f"""
You are an AI assistant designed to help developers log their work automatically.
Your task is to classify today's Git commits into the correct Redmine Feature (Parent Issue) based on the commit information.

CONTEXT:
Repository: {repository}
Redmine Project: {project_name}

AVAILABLE REDMINE FEATURES:
{features_list_str}
- '{self.default_feature}' (Default backup option)

{feedback_context}

COMMITS TO CLASSIFY:
{commits_list_str}

INSTRUCTIONS:
1. Match each commit into one of the AVAILABLE REDMINE FEATURES. 
2. If a commit fits into a specific Feature, return its exact name in 'feature_name'.
3. Assign a 'confidence' level from 0 to 100 for your decision.
4. If you are highly uncertain (e.g. general fixes, housekeeping) or if the commit doesn't fit any available features, set 'feature_name' to '{self.default_feature}'.
5. Give a detailed 'reason' explaining which files or descriptions guided your selection.
6. Support grouping multiple commits under the same feature.

OUTPUT FORMAT:
You MUST respond with a valid JSON object matching the following structure:
{{
    "selected_features": [
        {{
            "feature_name": "Name of Redmine Feature",
            "confidence": 95,
            "commits": ["hash1", "hash2"],
            "reason": "Because modified files show payment logic updates."
        }}
    ]
}}
Do not write any notes, conversational text, or markdown code block markers. Return only raw JSON.
"""
        return prompt.strip()

    def classify_commits(
        self,
        repository: str,
        project_name: str,
        commits: List[Commit],
        features: List[RedmineFeature],
        feedback_logs: List[FeedbackLog]
    ) -> AIClassificationResult:
        """Invokes the AI provider to classify the commits and maps the results to actual features."""
        if not commits:
            return AIClassificationResult(selected_features=[])

        prompt = self.build_prompt(repository, project_name, commits, features, feedback_logs)
        
        try:
            raw_response = self.ai_provider.classify(prompt)
            # Strip potential markdown formatting if returned by AI models
            cleaned_response = raw_response.strip()
            if cleaned_response.startswith("```"):
                # strip out ```json and ```
                lines = cleaned_response.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_response = "\n".join(lines).strip()
            
            data = json.loads(cleaned_response)
            parsed = AIClassificationResult(**data)
            
            # Map predictions to actual features using string matching
            resolved_selections: List[FeatureMappingSelection] = []
            
            feature_names = [f.subject for f in features]
            # Ensure default feature is in available matches
            if self.default_feature not in feature_names:
                feature_names.append(self.default_feature)

            for selection in parsed.selected_features:
                predicted_name = selection.feature_name.strip()
                
                # Check confidence threshold
                if selection.confidence < self.confidence_threshold:
                    logger.info(
                        f"AI confidence ({selection.confidence}%) for feature '{predicted_name}' "
                        f"is below threshold ({self.confidence_threshold}%). Falling back to default '{self.default_feature}'."
                    )
                    resolved_name = self.default_feature
                else:
                    # Resolve closest string match in actual features
                    match = process.extractOne(
                        predicted_name,
                        feature_names,
                        processor=fuzz_utils.default_process
                    )
                    if match and match[1] >= 80:  # 80% similarity threshold
                        resolved_name = match[0]
                        logger.info(f"Resolved AI predicted feature '{predicted_name}' to '{resolved_name}' (Score: {match[1]:.1f}%)")
                    else:
                        logger.warning(
                            f"AI predicted feature '{predicted_name}' did not match any available features. "
                            f"Falling back to default '{self.default_feature}'."
                        )
                        resolved_name = self.default_feature
                
                resolved_selections.append(FeatureMappingSelection(
                    feature_name=resolved_name,
                    confidence=selection.confidence,
                    commits=selection.commits,
                    reason=selection.reason
                ))
            
            return AIClassificationResult(selected_features=resolved_selections)

        except Exception as e:
            logger.error(f"AI classification failed or returned invalid output: {e}. Falling back to default feature.")
            # Fallback: All commits go to default feature
            all_hashes = [c.hash for c in commits]
            return AIClassificationResult(
                selected_features=[
                    FeatureMappingSelection(
                        feature_name=self.default_feature,
                        confidence=0,
                        commits=all_hashes,
                        reason=f"Fallback triggered due to AI error: {e}"
                    )
                ]
            )
