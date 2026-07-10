import os
import re
from typing import Dict, List, Optional
import yaml
from loguru import logger
from rapidfuzz import fuzz, utils as fuzz_utils
from app.models.domain import DiscoveredRepo, RedmineProject


class MappingResolver:
    """Resolves Git repositories to Redmine projects via YAML overrides and fuzzy name matching."""

    # Common suffixes that dilute repo↔project similarity
    _SUFFIX_RE = re.compile(
        r"[-_]?(be|fe|backend|frontend|api|web|app|service|svc|dashboard)$",
        re.IGNORECASE,
    )

    def __init__(self, mappings_path: str, match_threshold: int = 70):
        self.mappings_path = mappings_path
        self.match_threshold = match_threshold
        # repo full_name (lower) -> redmine project name
        self.mappings: Dict[str, str] = {}
        # optional explicit provider per repo
        self.providers: Dict[str, str] = {}
        self.load_mappings()

    def load_mappings(self) -> None:
        """Loads optional override mappings from the YAML file."""
        if not os.path.exists(self.mappings_path):
            logger.warning(
                f"Mappings file not found at '{self.mappings_path}'. "
                "Relying on fuzzy project matching only."
            )
            self.mappings = {}
            self.providers = {}
            return

        try:
            with open(self.mappings_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # Support both "repositories" (legacy) and "overrides"
            repos = data.get("overrides") or data.get("repositories") or {}
            self.mappings = {}
            self.providers = {}

            for repo_name, config in repos.items():
                key = repo_name.lower().strip()
                if isinstance(config, dict) and "redmine_project" in config:
                    self.mappings[key] = config["redmine_project"]
                    provider = config.get("provider")
                    if provider:
                        self.providers[key] = str(provider).lower().strip()
                elif isinstance(config, str):
                    self.mappings[key] = config

            logger.info(
                f"Loaded {len(self.mappings)} repository override(s) from '{self.mappings_path}'."
            )
        except Exception as e:
            logger.error(f"Error reading mapping configuration from '{self.mappings_path}': {e}")
            self.mappings = {}
            self.providers = {}

    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalizes a repo or project name for fuzzy comparison."""
        text = value.replace("_", " ").replace("-", " ").replace("/", " ")
        text = cls._SUFFIX_RE.sub("", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def resolve_project(
        self,
        repository: str,
        redmine_projects: Optional[List[RedmineProject]] = None,
        repo_short_name: Optional[str] = None,
    ) -> Optional[str]:
        """Resolves a repository to a Redmine project name (override first, then fuzzy match)."""
        repo_key = repository.lower().strip()

        # 1. Explicit YAML override
        if repo_key in self.mappings:
            return self.mappings[repo_key]

        if not redmine_projects:
            logger.warning(
                f"No Redmine project mapping found for repository '{repository}' "
                "and no project list provided for fuzzy matching."
            )
            return None

        # 2. Fuzzy match short name (and full path) against Redmine project names
        short = repo_short_name or repository.split("/")[-1]
        project_names = [p.name for p in redmine_projects]
        queries = [short, repository.split("/")[-1]]

        best_name: Optional[str] = None
        best_score: float = -1.0

        for query in queries:
            for project_name in project_names:
                score = float(
                    fuzz.token_set_ratio(
                        self.normalize_name(query),
                        self.normalize_name(project_name),
                    )
                )
                # Also try raw default_process comparison
                score2 = float(
                    fuzz.token_set_ratio(
                        fuzz_utils.default_process(query),
                        fuzz_utils.default_process(project_name),
                    )
                )
                score = max(score, score2)
                if score > best_score:
                    best_score = score
                    best_name = project_name

        if best_name and best_score >= self.match_threshold:
            logger.info(
                f"Fuzzy-matched repo '{repository}' → Redmine project '{best_name}' "
                f"(score {best_score:.1f}%)"
            )
            return best_name

        logger.warning(
            f"Could not match repository '{repository}' to any Redmine project "
            f"(best score {best_score:.1f}%, threshold {self.match_threshold})."
        )
        return None

    def resolve_provider(self, repository: str, discovered: Optional[DiscoveredRepo] = None) -> Optional[str]:
        """Returns explicit provider override, else the discovered provider."""
        repo_key = repository.lower().strip()
        if repo_key in self.providers:
            return self.providers[repo_key]
        if discovered:
            return discovered.provider
        return None
