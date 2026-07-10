from datetime import datetime
from typing import List, Optional, Literal
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
    provider: Optional[str] = None  # "github" | "gitlab"

class DiscoveredRepo(BaseModel):
    """A repository discovered from GitHub or GitLab."""
    full_name: str  # e.g. "org/repo"
    name: str  # short name used for fuzzy matching
    provider: Literal["github", "gitlab"]

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

class ClassifiedCommit(BaseModel):
    """A commit paired with its resolved Redmine project and feature."""
    commit: Commit
    project_name: str
    project_id: int
    feature_name: str
    parent_issue_id: Optional[int] = None

class WorkTodo(BaseModel):
    """A planned daily to-do with allocated hours."""
    subject: str
    description: str
    hours: float
    project_id: int
    project_name: str
    feature_name: str
    parent_issue_id: Optional[int] = None
    commits: List[Commit] = Field(default_factory=list)
    is_synthetic: bool = False  # True when padded to meet min to-do count

class SyncResult(BaseModel):
    """Result of the synchronization workflow run."""
    date: str
    processed_commits_count: int
    created_issues: List[int] = Field(default_factory=list)
    updated_issues: List[int] = Field(default_factory=list)
    time_entries_created: int = 0
    hours_logged: float = 0.0
    todos_planned: int = 0
    cached_commits_count: int = 0
    errors: List[str] = Field(default_factory=list)
    unmapped_repos: List[str] = Field(default_factory=list)
    planned_todos: List[WorkTodo] = Field(default_factory=list)
    dry_run: bool = False
