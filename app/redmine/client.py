from typing import List, Dict, Any, Optional, Tuple
import requests
from loguru import logger
from app.models.domain import RedmineProject, RedmineFeature
from app.utils.helpers import with_retry

# Prefer these trackers when creating child to-dos vs parent features
_CHILD_TRACKER_NAMES = ("to-do", "todo", "task", "issue", "bug", "support", "development")
_PARENT_TRACKER_NAMES = ("feature", "epic", "user story", "parent task", "parent")


class RedmineAPIError(Exception):
    """Redmine HTTP error with parsed validation details (do not retry 4xx)."""

    def __init__(self, status_code: int, path: str, message: str, errors: Optional[List[str]] = None):
        self.status_code = status_code
        self.path = path
        self.errors = errors or []
        super().__init__(message)


class RedmineClient:
    """Interacts with Redmine REST API to search and manage projects, features, and tasks."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-Redmine-API-Key": api_key,
            "Content-Type": "application/json",
        }
        self._trackers_by_project: Dict[int, List[Dict[str, Any]]] = {}

    @with_retry(
        exceptions=(
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        )
    )
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.request(
            method, url, headers=self.headers, params=params, json=json_data, timeout=30
        )
        if not response.ok:
            errors: List[str] = []
            detail = response.text[:800]
            try:
                payload = response.json()
                raw_errors = payload.get("errors")
                if isinstance(raw_errors, list):
                    errors = [str(e) for e in raw_errors]
                    detail = "; ".join(errors)
                elif isinstance(payload.get("error"), str):
                    detail = payload["error"]
                    errors = [detail]
            except Exception:
                pass
            raise RedmineAPIError(
                response.status_code,
                path,
                f"{response.status_code} for {path}: {detail}",
                errors=errors,
            )
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
                    projects.append(
                        RedmineProject(
                            id=p["id"],
                            name=p["name"],
                            identifier=p["identifier"],
                            description=p.get("description", ""),
                        )
                    )

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
            if (
                p.identifier == project_identifier_or_name
                or p.name.lower() == project_identifier_or_name.lower()
            ):
                return p
        return None

    def get_project_trackers(self, project_id: int) -> List[Dict[str, Any]]:
        """Trackers enabled on a project: [{id, name}, ...]."""
        if project_id in self._trackers_by_project:
            return self._trackers_by_project[project_id]
        try:
            response = self._request(
                "GET", f"projects/{project_id}.json", params={"include": "trackers"}
            )
            trackers = response.json().get("project", {}).get("trackers") or []
            self._trackers_by_project[project_id] = trackers
            return trackers
        except Exception as e:
            logger.warning(f"Could not load trackers for project {project_id}: {e}")
            return []

    def _pick_tracker_id(
        self, project_id: int, *, for_parent: bool
    ) -> Optional[int]:
        trackers = self.get_project_trackers(project_id)
        if not trackers:
            return None
        preferred = _PARENT_TRACKER_NAMES if for_parent else _CHILD_TRACKER_NAMES
        lowered = [(t, (t.get("name") or "").strip().lower()) for t in trackers]
        for want in preferred:
            for tracker, name in lowered:
                if name == want or want in name:
                    return int(tracker["id"])
        # Child: avoid Feature/Epic if possible
        if not for_parent:
            for tracker, name in lowered:
                if not any(p in name for p in _PARENT_TRACKER_NAMES):
                    return int(tracker["id"])
        return int(trackers[0]["id"])

    def get_features(self, project_id: int) -> List[RedmineFeature]:
        """Fetches features of a project. Features are represented as Parent Issues (without parents themselves)."""
        features: List[RedmineFeature] = []
        offset = 0
        limit = 100

        try:
            while True:
                params = {
                    "project_id": project_id,
                    "parent_id": "!*",
                    "status_id": "*",
                    "offset": offset,
                    "limit": limit,
                }
                response = self._request("GET", "issues.json", params=params)
                data = response.json()
                issue_list = data.get("issues", [])
                if not issue_list:
                    break

                for issue in issue_list:
                    features.append(
                        RedmineFeature(
                            id=issue["id"],
                            subject=issue["subject"],
                            description=issue.get("description", ""),
                            project_id=project_id,
                        )
                    )

                if len(issue_list) < limit:
                    break
                offset += limit
        except Exception as e:
            logger.error(f"Failed to fetch Features for project {project_id}: {e}")
            raise e

        return features

    def find_feature_by_subject(
        self, project_id: int, subject: str
    ) -> Optional[RedmineFeature]:
        """Finds a root feature issue by subject (case-insensitive)."""
        target = (subject or "").strip().lower()
        if not target:
            return None
        for feature in self.get_features(project_id):
            if feature.subject.strip().lower() == target:
                return feature
        return None

    def ensure_feature(self, project_id: int, subject: str) -> RedmineFeature:
        """Returns an existing root feature or creates one so to-dos always have a parent."""
        name = (subject or "").strip() or "General Development"
        existing = self.find_feature_by_subject(project_id, name)
        if existing:
            return existing

        logger.warning(
            f"Feature '{name}' not found as a root issue in project {project_id}; creating it."
        )
        issue = self.create_issue(
            project_id=project_id,
            parent_issue_id=None,
            subject=name[:255],
            description=(
                "Parent feature for CommitFlow daily to-dos.\n\n"
                f"Auto-created because '{name}' was missing as a root Redmine issue."
            ),
            for_parent=True,
        )
        return RedmineFeature(
            id=int(issue["id"]),
            subject=issue.get("subject") or name,
            description=issue.get("description") or "",
            project_id=project_id,
        )

    def search_today_issue(
        self, project_id: int, parent_issue_id: int, date_str: str
    ) -> Optional[Dict[str, Any]]:
        """Searches if a child issue (work log) exists for the given parent under today's date."""
        target_subject = f"Daily Development Update - {date_str}"
        return self.find_issue_by_subject(
            project_id=project_id,
            subject=target_subject,
            parent_issue_id=parent_issue_id,
        )

    def create_issue(
        self,
        project_id: int,
        parent_issue_id: Optional[int],
        subject: str,
        description: str,
        *,
        for_parent: bool = False,
        tracker_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Creates a new issue in Redmine, optionally as a child issue."""
        clean_subject = (subject or "").strip()[:255]
        clean_description = (description or "")[:60000]
        payload: Dict[str, Any] = {
            "issue": {
                "project_id": project_id,
                "subject": clean_subject,
                "description": clean_description,
            }
        }
        chosen_tracker = tracker_id or self._pick_tracker_id(
            project_id, for_parent=for_parent or not parent_issue_id
        )
        if chosen_tracker:
            payload["issue"]["tracker_id"] = chosen_tracker
        if parent_issue_id:
            payload["issue"]["parent_issue_id"] = int(parent_issue_id)

        try:
            response = self._request("POST", "issues.json", json_data=payload)
            issue_data = response.json().get("issue", {})
            logger.info(
                f"Created Redmine issue #{issue_data.get('id')} - '{clean_subject}'"
                + (f" under #{parent_issue_id}" if parent_issue_id else " (root)")
            )
            return issue_data
        except RedmineAPIError as e:
            # Parent/tracker mismatch — retry once as root-less only when creating a parent feature
            # For children: retry without parent only if explicitly no parent wanted
            if parent_issue_id and e.status_code == 422:
                logger.warning(
                    f"Create under parent #{parent_issue_id} rejected ({e}). "
                    "Retrying with alternate child tracker if available."
                )
                trackers = self.get_project_trackers(project_id)
                tried = {chosen_tracker}
                for tracker in trackers:
                    tid = int(tracker["id"])
                    if tid in tried:
                        continue
                    name = (tracker.get("name") or "").lower()
                    if any(p in name for p in _PARENT_TRACKER_NAMES):
                        continue
                    tried.add(tid)
                    payload["issue"]["tracker_id"] = tid
                    try:
                        response = self._request("POST", "issues.json", json_data=payload)
                        issue_data = response.json().get("issue", {})
                        logger.info(
                            f"Created Redmine issue #{issue_data.get('id')} "
                            f"with tracker '{tracker.get('name')}' under #{parent_issue_id}"
                        )
                        return issue_data
                    except RedmineAPIError:
                        continue
            logger.error(f"Failed to create Redmine issue '{clean_subject}': {e}")
            raise

    def update_issue(self, issue_id: int, description: str) -> None:
        """Updates the description of an existing issue."""
        payload = {"issue": {"description": description}}
        try:
            self._request("PUT", f"issues/{issue_id}.json", json_data=payload)
            logger.info(f"Updated Redmine issue #{issue_id} description.")
        except Exception as e:
            logger.error(f"Failed to update Redmine issue #{issue_id}: {e}")
            raise e

    def add_note(self, issue_id: int, note: str) -> None:
        """Adds a journal comment (note) to an existing issue."""
        payload = {"issue": {"notes": note}}
        try:
            self._request("PUT", f"issues/{issue_id}.json", json_data=payload)
            logger.info(f"Added note to Redmine issue #{issue_id}.")
        except Exception as e:
            logger.error(f"Failed to add note to Redmine issue #{issue_id}: {e}")
            raise e

    @staticmethod
    def _subjects_match(a: str, b: str) -> bool:
        return (a or "").strip().lower() == (b or "").strip().lower()

    def _scan_issues_for_subject(
        self,
        project_id: int,
        subject: str,
        *,
        parent_issue_id: Optional[int] = None,
        limit_pages: int = 20,
    ) -> Optional[Dict[str, Any]]:
        offset = 0
        limit = 100
        pages = 0
        target = subject.strip()

        while pages < limit_pages:
            params: Dict[str, Any] = {
                "project_id": project_id,
                "status_id": "*",
                "offset": offset,
                "limit": limit,
                "sort": "id:desc",
            }
            if parent_issue_id:
                params["parent_id"] = parent_issue_id

            response = self._request("GET", "issues.json", params=params)
            issues = response.json().get("issues", [])
            if not issues:
                break

            for issue in issues:
                if self._subjects_match(issue.get("subject", ""), target):
                    return issue

            if len(issues) < limit:
                break
            offset += limit
            pages += 1
        return None

    def find_issue_by_subject(
        self,
        project_id: int,
        subject: str,
        parent_issue_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Finds an issue by subject — prefer under parent, then anywhere in the project."""
        target = (subject or "").strip()
        if not target:
            return None

        try:
            if parent_issue_id:
                found = self._scan_issues_for_subject(
                    project_id, target, parent_issue_id=parent_issue_id
                )
                if found:
                    return found

            # Idempotency: already created (maybe under another parent / open)
            found = self._scan_issues_for_subject(project_id, target, parent_issue_id=None)
            if found:
                logger.info(
                    f"Found existing issue #{found.get('id')} by subject "
                    f"(project-wide) for '{target[:80]}'"
                )
            return found
        except Exception as e:
            logger.error(f"Error searching for issue '{subject}': {e}")
            return None

    def create_time_entry(
        self,
        issue_id: int,
        hours: float,
        spent_on: str,
        comments: str = "",
    ) -> Dict[str, Any]:
        """Logs spent time against a Redmine issue for a given date (YYYY-MM-DD)."""
        payload = {
            "time_entry": {
                "issue_id": issue_id,
                "spent_on": spent_on,
                "hours": hours,
                "comments": comments[:255] if comments else "",
            }
        }
        try:
            response = self._request("POST", "time_entries.json", json_data=payload)
            entry = response.json().get("time_entry", {})
            logger.info(
                f"Logged {hours}h on issue #{issue_id} for {spent_on} "
                f"(time entry #{entry.get('id')})."
            )
            return entry
        except Exception as e:
            logger.error(f"Failed to create time entry on issue #{issue_id}: {e}")
            raise e

    def get_time_entries_for_issue_on_date(
        self, issue_id: int, spent_on: str
    ) -> List[Dict[str, Any]]:
        """Returns time entries for an issue on a specific date."""
        try:
            params = {
                "issue_id": issue_id,
                "spent_on": spent_on,
                "limit": 100,
            }
            response = self._request("GET", "time_entries.json", params=params)
            return response.json().get("time_entries", [])
        except Exception as e:
            logger.error(f"Failed to fetch time entries for issue #{issue_id}: {e}")
            return []

    def list_time_entries_for_date(self, spent_on: str) -> List[Dict[str, Any]]:
        """List the current user's time entries for a spent_on date (YYYY-MM-DD)."""
        entries: List[Dict[str, Any]] = []
        offset = 0
        limit = 100

        try:
            while True:
                params = {
                    "spent_on": spent_on,
                    "user_id": "me",
                    "offset": offset,
                    "limit": limit,
                }
                response = self._request("GET", "time_entries.json", params=params)
                data = response.json()
                batch = data.get("time_entries", [])
                if not batch:
                    break

                for entry in batch:
                    issue = entry.get("issue") or {}
                    project = entry.get("project") or {}
                    entries.append(
                        {
                            "id": entry.get("id"),
                            "hours": float(entry.get("hours") or 0),
                            "spent_on": entry.get("spent_on") or spent_on,
                            "comments": entry.get("comments") or "",
                            "issue_id": issue.get("id"),
                            "issue_subject": issue.get("name") or "",
                            "project_name": project.get("name") or "",
                        }
                    )

                if len(batch) < limit:
                    break
                offset += limit
        except Exception as e:
            logger.error(f"Failed to list time entries for {spent_on}: {e}")
            raise e

        return entries
