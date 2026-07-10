import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from loguru import logger
from app.models.domain import Commit, DiscoveredRepo
from app.utils.helpers import with_retry, is_merge_commit

class GitHubClient:
    """Interacts with GitHub REST API to retrieve user commits and change statistics."""

    def __init__(self, token: Optional[str] = None):
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.base_url = "https://api.github.com"

    def get_authenticated_user(self) -> Optional[str]:
        """Returns the authenticated user's display name (or login) via GET /user."""
        try:
            response = self._request("GET", "/user")
            data = response.json()
            # Prefer the display name; fall back to the login handle
            return data.get("name") or data.get("login")
        except Exception as e:
            logger.warning(f"Could not resolve GitHub authenticated user: {e}")
            return None

    def list_repos(self) -> List[DiscoveredRepo]:
        """Lists repositories accessible to the authenticated user."""
        repos: List[DiscoveredRepo] = []
        page = 1
        per_page = 100

        try:
            while True:
                params = {
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                }
                response = self._request("GET", "/user/repos", params=params)
                data = response.json()
                if not data:
                    break

                for item in data:
                    full_name = item.get("full_name", "")
                    if not full_name:
                        continue
                    repos.append(DiscoveredRepo(
                        full_name=full_name,
                        name=item.get("name") or full_name.split("/")[-1],
                        provider="github",
                    ))

                if len(data) < per_page:
                    break
                page += 1
        except Exception as e:
            logger.error(f"Failed to list GitHub repositories: {e}")
            raise e

        logger.info(f"Discovered {len(repos)} GitHub repositories.")
        return repos

    @with_retry()
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.request(method, url, headers=self.headers, params=params, timeout=15)
        
        # Check rate-limit headers
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining and int(remaining) == 0:
            reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            sleep_dur = max(reset_time - int(time.time()), 10)
            logger.warning(f"GitHub Rate limit reached. Sleeping for {sleep_dur}s...")
            time.sleep(sleep_dur)
            return self._request(method, path, params)
            
        response.raise_for_status()
        return response

    def fetch_commits(
        self,
        repository: str,
        author_name: str,
        since: datetime,
        until: datetime
    ) -> List[Commit]:
        """Fetches commit details from a repository within a datetime range, filtered by author."""
        commits: List[Commit] = []
        page = 1
        per_page = 100

        logger.info(f"Fetching GitHub commits from '{repository}' since {since.isoformat()} until {until.isoformat()}...")

        try:
            while True:
                params = {
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "page": page,
                    "per_page": per_page
                }
                
                response = self._request("GET", f"repos/{repository}/commits", params=params)
                data = response.json()
                if not data:
                    break

                for item in data:
                    commit_data = item.get("commit", {})
                    author_data = commit_data.get("author", {})
                    committer_data = commit_data.get("committer", {})
                    
                    git_author_name = author_data.get("name", "")
                    git_committer_name = committer_data.get("name", "")
                    
                    # Fuzzy match or exact match on author name
                    match_author = (
                        author_name.lower() in git_author_name.lower() or 
                        author_name.lower() in git_committer_name.lower() or
                        (item.get("author") and author_name.lower() in item["author"].get("login", "").lower())
                    )
                    
                    if not match_author:
                        continue

                    sha = item.get("sha", "")
                    message_full = commit_data.get("message", "")
                    msg_lines = message_full.split("\n", 1)
                    subject = msg_lines[0]
                    description = msg_lines[1] if len(msg_lines) > 1 else ""

                    parents = item.get("parents") or []
                    if is_merge_commit(subject, parent_count=len(parents)):
                        logger.info(
                            f"Skipping merge commit {sha[:8]} in '{repository}': {subject[:80]}"
                        )
                        continue

                    # Fetch commit details (for changed files)
                    detail = self.fetch_commit_detail(repository, sha)
                    changed_files = [f.get("filename", "") for f in detail.get("files", [])]
                    stats = detail.get("stats", {})

                    committed_date = datetime.strptime(
                        author_data.get("date", committer_data.get("date", since.isoformat())),
                        "%Y-%m-%dT%H:%M:%SZ"
                    )

                    commits.append(Commit(
                        hash=sha,
                        message=subject,
                        description=description,
                        author=git_author_name,
                        repository=repository,
                        committed_date=committed_date,
                        url=item.get("html_url"),
                        changed_files=changed_files,
                        additions=stats.get("additions", 0),
                        deletions=stats.get("deletions", 0),
                        provider="github",
                    ))

                if len(data) < per_page:
                    break
                page += 1

        except Exception as e:
            logger.error(f"Failed to fetch GitHub commits for repo '{repository}': {e}")
            raise e

        logger.info(f"Found {len(commits)} commits by user '{author_name}' in GitHub repo '{repository}'.")
        return commits

    def fetch_commit_detail(self, repository: str, sha: str) -> Dict[str, Any]:
        """Fetches detailed metrics and changed files for a specific commit."""
        try:
            response = self._request("GET", f"repos/{repository}/commits/{sha}")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching commit details for '{sha}' in '{repository}': {e}")
            return {}
