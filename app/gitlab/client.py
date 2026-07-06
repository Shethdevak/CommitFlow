import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from loguru import logger
from app.models.domain import Commit
from app.utils.helpers import with_retry

class GitLabClient:
    """Interacts with GitLab REST API (Cloud or Self-Hosted) to retrieve user commits."""

    def __init__(self, token: Optional[str] = None, base_url: str = "https://gitlab.com"):
        self.headers = {}
        if token:
            self.headers["PRIVATE-TOKEN"] = token
        # Strip trailing slash from base url and append api version
        self.base_url = f"{base_url.rstrip('/')}/api/v4"

    @with_retry()
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.request(method, url, headers=self.headers, params=params, timeout=15)
        response.raise_for_status()
        return response

    def get_authenticated_user(self) -> Optional[str]:
        """Returns the authenticated user's display name (or username) via GET /user."""
        try:
            response = self._request("GET", "/user")
            data = response.json()
            # Prefer the full name; fall back to username
            return data.get("name") or data.get("username")
        except Exception as e:
            logger.warning(f"Could not resolve GitLab authenticated user: {e}")
            return None

    def fetch_commits(
        self,
        repository: str,
        author_name: str,
        since: datetime,
        until: datetime
    ) -> List[Commit]:
        """Fetches commits from a GitLab project within a time window, filtering by author."""
        commits: List[Commit] = []
        page = 1
        per_page = 100

        # GitLab requires project paths to be URL-encoded (e.g. 'group/project' becomes 'group%2Fproject')
        project_path_encoded = urllib.parse.quote_plus(repository)
        logger.info(f"Fetching GitLab commits from '{repository}' since {since.isoformat()} until {until.isoformat()}...")

        try:
            while True:
                params = {
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "all": "true",   # search across ALL branches, not just default
                    "page": page,
                    "per_page": per_page
                }
                
                response = self._request("GET", f"projects/{project_path_encoded}/repository/commits", params=params)
                data = response.json()
                if not data:
                    break

                for item in data:
                    git_author_name = item.get("author_name", "")
                    git_author_email = item.get("author_email", "")
                    
                    # Match author name or email
                    match_author = (
                        author_name.lower() in git_author_name.lower() or 
                        author_name.lower() in git_author_email.lower()
                    )
                    
                    if not match_author:
                        continue

                    sha = item.get("id", "")
                    message_full = item.get("message", "")
                    msg_lines = message_full.split("\n", 1)
                    subject = msg_lines[0]
                    description = msg_lines[1] if len(msg_lines) > 1 else ""

                    # Fetch changed files
                    changed_files = self.fetch_changed_files(project_path_encoded, sha)
                    
                    stats = item.get("stats") or {}
                    additions = stats.get("additions", 0)
                    deletions = stats.get("deletions", 0)

                    committed_date = datetime.fromisoformat(
                        item.get("created_at", since.isoformat()).replace("Z", "+00:00")
                    ).replace(tzinfo=None)

                    # Construct commit URL
                    commit_url = f"{self.base_url.replace('/api/v4', '')}/{repository}/-/commit/{sha}"

                    commits.append(Commit(
                        hash=sha,
                        message=subject,
                        description=description,
                        author=git_author_name,
                        repository=repository,
                        committed_date=committed_date,
                        url=commit_url,
                        changed_files=changed_files,
                        additions=additions,
                        deletions=deletions
                    ))

                if len(data) < per_page:
                    break
                page += 1

        except Exception as e:
            logger.error(f"Failed to fetch GitLab commits for repo '{repository}': {e}")
            raise e

        logger.info(f"Found {len(commits)} commits by user '{author_name}' in GitLab repo '{repository}'.")
        return commits

    def fetch_changed_files(self, project_path_encoded: str, sha: str) -> List[str]:
        """Fetches the list of files modified in a specific commit."""
        try:
            response = self._request("GET", f"projects/{project_path_encoded}/repository/commits/{sha}/diff")
            diffs = response.json()
            # extract paths from diff items
            changed = set()
            for d in diffs:
                if d.get("new_path"):
                    changed.add(d["new_path"])
                if d.get("old_path"):
                    changed.add(d["old_path"])
            return list(changed)
        except Exception as e:
            logger.error(f"Error fetching GitLab commit diffs for '{sha}': {e}")
            return []
