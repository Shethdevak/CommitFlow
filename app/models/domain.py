from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class Commit(BaseModel):
    """Represents a single Git commit from GitHub or GitLab."""
    hash: str
    message: str
    description: Optional[str] = ""
    author: str
    repository: str  # Format: "org/repo" or "group/project"
    committed_date: datetime
    url: Optional[str] = None
    changed_files: List[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0

class RedmineProject(BaseModel):
    """Represents a Redmine project entity."""
    id: int
    name: str
    identifier: str
    description: Optional[str] = ""

class RedmineFeature(BaseModel):
    """Represents a Redmine Feature (implemented as a Parent Issue)."""
    id: int
    subject: str
    description: Optional[str] = ""
    project_id: int

class FeatureMappingSelection(BaseModel):
    """Represents an AI mapping decision for a list of commits."""
    feature_name: str
    confidence: int
    commits: List[str]  # List of commit hashes
    reason: str

class AIClassificationResult(BaseModel):
    """Output structure expected from AI providers."""
    selected_features: List[FeatureMappingSelection]

class SyncResult(BaseModel):
    """Result of the synchronization workflow run."""
    date: str
    processed_commits_count: int
    created_issues: List[int] = Field(default_factory=list)
    updated_issues: List[int] = Field(default_factory=list)
    cached_commits_count: int = 0
    errors: List[str] = Field(default_factory=list)
