import os
from typing import Dict, Optional
import yaml
from loguru import logger

class MappingResolver:
    """Loads and resolves Git repository paths to Redmine projects based on a YAML map file."""

    def __init__(self, mappings_path: str):
        self.mappings_path = mappings_path
        self.mappings: Dict[str, str] = {}
        self.load_mappings()

    def load_mappings(self) -> None:
        """Loads mappings from the specified YAML file."""
        if not os.path.exists(self.mappings_path):
            logger.warning(f"Mappings file not found at '{self.mappings_path}'. No repository mappings will be loaded.")
            self.mappings = {}
            return

        try:
            with open(self.mappings_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            repos = data.get("repositories", {})
            self.mappings = {}
            for repo_name, config in repos.items():
                if isinstance(config, dict) and "redmine_project" in config:
                    self.mappings[repo_name.lower().strip()] = config["redmine_project"]
                elif isinstance(config, str):
                    self.mappings[repo_name.lower().strip()] = config
            
            logger.info(f"Successfully loaded {len(self.mappings)} repository mappings from '{self.mappings_path}'.")
        except Exception as e:
            logger.error(f"Error reading mapping configuration from '{self.mappings_path}': {e}")
            self.mappings = {}

    def resolve_project(self, repository: str) -> Optional[str]:
        """Resolves a repository path to its mapped Redmine project name."""
        repo_key = repository.lower().strip()
        project = self.mappings.get(repo_key)
        if not project:
            logger.warning(f"No Redmine project mapping found for repository '{repository}'. Please check your mappings file.")
            return None
        return project
