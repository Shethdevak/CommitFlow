from typing import List, Dict, Any, Optional
import requests
from loguru import logger
from app.models.domain import RedmineProject, RedmineFeature
from app.utils.helpers import with_retry

class RedmineClient:
    """Interacts with Redmine REST API to search and manage projects, features, and tasks."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-Redmine-API-Key": api_key,
            "Content-Type": "application/json"
        }

    @with_retry()
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, json_data: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.request(method, url, headers=self.headers, params=params, json=json_data, timeout=15)
        response.raise_for_status()
        return response

    def get_projects(self) -> List[RedmineProject]:
        """Fetches all projects from the Redmine server."""
        projects: List[RedmineProject] = []
        offset = 0
        limit = 100

        try:
            while True:
                params = {"offset": offset, "limit": limit}
                response = self._request("GET", "projects.json", params=params)
                data = response.json()
                proj_list = data.get("projects", [])
                if not proj_list:
                    break
                
                for p in proj_list:
                    projects.append(RedmineProject(
                        id=p["id"],
                        name=p["name"],
                        identifier=p["identifier"],
                        description=p.get("description", "")
                    ))
                
                if len(proj_list) < limit:
                    break
                offset += limit
        except Exception as e:
            logger.error(f"Failed to fetch Redmine projects: {e}")
            raise e

        return projects

    def get_project(self, project_identifier_or_name: str) -> Optional[RedmineProject]:
        """Finds a project by its identifier or matching name."""
        projects = self.get_projects()
        for p in projects:
            if p.identifier == project_identifier_or_name or p.name.lower() == project_identifier_or_name.lower():
                return p
        return None

    def get_features(self, project_id: int) -> List[RedmineFeature]:
        """Fetches features of a project. Features are represented as Parent Issues (without parents themselves)."""
        features: List[RedmineFeature] = []
        offset = 0
        limit = 100

        try:
            while True:
                # parent_id=!* returns issues that DO NOT have a parent (root parent tasks in Redmine)
                params = {
                    "project_id": project_id,
                    "parent_id": "!*",
                    "status_id": "*",  # get all statuses
                    "offset": offset,
                    "limit": limit
                }
                response = self._request("GET", "issues.json", params=params)
                data = response.json()
                issue_list = data.get("issues", [])
                if not issue_list:
                    break

                for issue in issue_list:
                    features.append(RedmineFeature(
                        id=issue["id"],
                        subject=issue["subject"],
                        description=issue.get("description", ""),
                        project_id=project_id
                    ))

                if len(issue_list) < limit:
                    break
                offset += limit
        except Exception as e:
            logger.error(f"Failed to fetch Features for project {project_id}: {e}")
            raise e

        return features

    def search_today_issue(self, project_id: int, parent_issue_id: int, date_str: str) -> Optional[Dict[str, Any]]:
        """Searches if a child issue (work log) exists for the given parent under today's date."""
        target_subject = f"Daily Development Update - {date_str}"
        offset = 0
        limit = 50

        try:
            while True:
                params = {
                    "project_id": project_id,
                    "parent_id": parent_issue_id,
                    "status_id": "*",
                    "offset": offset,
                    "limit": limit
                }
                response = self._request("GET", "issues.json", params=params)
                data = response.json()
                issues = data.get("issues", [])
                if not issues:
                    break

                for issue in issues:
                    if issue.get("subject", "").strip() == target_subject:
                        return issue

                if len(issues) < limit:
                    break
                offset += limit
        except Exception as e:
            logger.error(f"Error searching for existing work log child issue: {e}")

        return None

    def create_issue(
        self,
        project_id: int,
        parent_issue_id: Optional[int],
        subject: str,
        description: str
    ) -> Dict[str, Any]:
        """Creates a new issue in Redmine, optionally as a child issue."""
        payload = {
            "issue": {
                "project_id": project_id,
                "subject": subject,
                "description": description
            }
        }
        if parent_issue_id:
            payload["issue"]["parent_issue_id"] = parent_issue_id

        try:
            response = self._request("POST", "issues.json", json_data=payload)
            issue_data = response.json().get("issue", {})
            logger.info(f"Created Redmine issue #{issue_data.get('id')} - '{subject}'")
            return issue_data
        except Exception as e:
            logger.error(f"Failed to create Redmine issue '{subject}': {e}")
            raise e

    def update_issue(self, issue_id: int, description: str) -> None:
        """Updates the description of an existing issue."""
        payload = {
            "issue": {
                "description": description
            }
        }
        try:
            self._request("PUT", f"issues/{issue_id}.json", json_data=payload)
            logger.info(f"Updated Redmine issue #{issue_id} description.")
        except Exception as e:
            logger.error(f"Failed to update Redmine issue #{issue_id}: {e}")
            raise e

    def add_note(self, issue_id: int, note: str) -> None:
        """Adds a journal comment (note) to an existing issue."""
        payload = {
            "issue": {
                "notes": note
            }
        }
        try:
            self._request("PUT", f"issues/{issue_id}.json", json_data=payload)
            logger.info(f"Added note to Redmine issue #{issue_id}.")
        except Exception as e:
            logger.error(f"Failed to add note to Redmine issue #{issue_id}: {e}")
            raise e
