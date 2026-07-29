from typing import List, Dict, Any, Optional
import re
import requests
from loguru import logger
from app.models.domain import RedmineProject, RedmineFeature
from app.utils.helpers import with_retry

# Digiflux / CommitFlow convention:
#   Feature  = parent (product area)
#   To-Do    = child work item where time is logged
# Never create worklogs as Support/Meeting, Bug, Planning, etc.
_PARENT_TRACKER_KEYS = ("feature",)
_CHILD_TRACKER_KEYS = ("todo", "todos")  # matches "To-Do", "Todo", "To Do"
_BLOCKED_PARENT_KEYS = (
    "support",
    "meeting",
    "supportmeeting",
    "planning",
    "backlog",
    "bug",
    "todo",
    "todos",
)
_BLOCKED_CHILD_KEYS = (
    "support",
    "meeting",
    "supportmeeting",
    "planning",
    "backlog",
    "bug",
    "feature",
    "epic",
)


def _tracker_key(name: str) -> str:
    """Normalize tracker name: 'To-Do' → 'todo', 'Support/Meeting' → 'supportmeeting'."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _is_feature_tracker(name: str) -> bool:
    key = _tracker_key(name)
    if not key or key in _BLOCKED_PARENT_KEYS:
        return False
    return key == "feature" or key.startswith("feature")


def _is_todo_tracker(name: str) -> bool:
    key = _tracker_key(name)
    if not key or key in _BLOCKED_CHILD_KEYS:
        return False
    return key in _CHILD_TRACKER_KEYS or ("todo" in key and key not in _BLOCKED_CHILD_KEYS)


def _issue_tracker_name(issue: Dict[str, Any]) -> str:
    return ((issue.get("tracker") or {}).get("name") or "").strip()


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
        self._current_user_id: Optional[int] = None

    def get_current_user_id(self) -> Optional[int]:
        """Redmine user id for this API key ('me'). Cached per client instance."""
        if self._current_user_id is not None:
            return self._current_user_id
        try:
            response = self._request("GET", "users/current.json")
            user = response.json().get("user") or {}
            uid = user.get("id")
            if uid is not None:
                self._current_user_id = int(uid)
                logger.info(
                    f"Redmine current user #{self._current_user_id} "
                    f"({user.get('login') or user.get('firstname') or 'me'})"
                )
                return self._current_user_id
        except Exception as e:
            logger.warning(f"Could not resolve Redmine current user (assignee): {e}")
        return None

    def ensure_todo_assignment(self, issue_id: int) -> None:
        """Force assignee = me and % Done = 100 on a worklog To-Do."""
        issue_fields: Dict[str, Any] = {"done_ratio": 100}
        uid = self.get_current_user_id()
        if uid is not None:
            issue_fields["assigned_to_id"] = uid
        try:
            self._request(
                "PUT", f"issues/{int(issue_id)}.json", json_data={"issue": issue_fields}
            )
            logger.info(
                f"Set issue #{issue_id} assignee="
                f"{uid if uid is not None else 'unchanged'} done_ratio=100"
            )
        except Exception as e:
            logger.warning(
                f"Could not set assignee/% Done on issue #{issue_id}: {e}"
            )

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
        """Pick Feature tracker for parents, To-Do tracker for worklog children."""
        trackers = self.get_project_trackers(project_id)
        if not trackers:
            return None

        keyed = [(t, _tracker_key(t.get("name") or "")) for t in trackers]
        wanted = _PARENT_TRACKER_KEYS if for_parent else _CHILD_TRACKER_KEYS

        for key in wanted:
            for tracker, norm in keyed:
                if norm == key:
                    return int(tracker["id"])

        if for_parent:
            for tracker, norm in keyed:
                if norm.startswith("feature"):
                    return int(tracker["id"])
            logger.error(
                f"Project {project_id} has no Feature tracker "
                f"(found: {[t.get('name') for t in trackers]})"
            )
            return None

        # Children: To-Do only — never Support/Meeting / Bug / Planning
        for tracker, norm in keyed:
            if "todo" in norm and norm not in _BLOCKED_CHILD_KEYS:
                return int(tracker["id"])

        logger.error(
            f"Project {project_id} has no To-Do tracker "
            f"(found: {[t.get('name') for t in trackers]}). "
            "Refusing to create Support/Meeting or other wrong trackers."
        )
        return None

    def get_features(self, project_id: int) -> List[RedmineFeature]:
        """Fetches Feature-tracker issues (parents for To-Do worklogs)."""
        features: List[RedmineFeature] = []
        offset = 0
        limit = 100
        feature_tracker_id = self._pick_tracker_id(project_id, for_parent=True)

        try:
            while True:
                params: Dict[str, Any] = {
                    "project_id": project_id,
                    "status_id": "*",
                    "offset": offset,
                    "limit": limit,
                }
                # Prefer Feature tracker only — not every root issue (Support/Meeting, Planning, …)
                if feature_tracker_id:
                    params["tracker_id"] = feature_tracker_id
                else:
                    params["parent_id"] = "!*"

                response = self._request("GET", "issues.json", params=params)
                data = response.json()
                issue_list = data.get("issues", [])
                if not issue_list:
                    break

                for issue in issue_list:
                    tracker = _issue_tracker_name(issue)
                    # Always validate client-side — Redmine tracker_id filter is not enough.
                    # Previously Support/Meeting roots (e.g. #36408 "meeting") leaked in as "features".
                    if not _is_feature_tracker(tracker):
                        logger.debug(
                            f"Skipping non-Feature issue #{issue.get('id')} "
                            f"tracker={tracker!r} subject={issue.get('subject', '')[:60]!r}"
                        )
                        continue
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

        logger.info(
            f"Loaded {len(features)} Feature parent(s) for project {project_id}"
            + (f" (tracker_id={feature_tracker_id})" if feature_tracker_id else "")
        )
        return features

    def get_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single Redmine issue by id."""
        try:
            response = self._request("GET", f"issues/{int(issue_id)}.json")
            return response.json().get("issue")
        except Exception as e:
            logger.error(f"Failed to fetch issue #{issue_id}: {e}")
            return None

    def is_feature_issue(self, issue: Dict[str, Any]) -> bool:
        return _is_feature_tracker(_issue_tracker_name(issue))

    def is_todo_issue(self, issue: Dict[str, Any]) -> bool:
        return _is_todo_tracker(_issue_tracker_name(issue))

    def assert_feature_parent(self, issue_id: int) -> Optional[RedmineFeature]:
        """Return the issue only if it is a Feature tracker parent; else None."""
        issue = self.get_issue(issue_id)
        if not issue:
            return None
        tracker = _issue_tracker_name(issue)
        if not self.is_feature_issue(issue):
            logger.warning(
                f"Rejecting parent #{issue_id} tracker={tracker!r} "
                f"subject={issue.get('subject', '')[:60]!r} — not a Feature "
                "(Support/Meeting and similar cannot parent CommitFlow To-Dos)."
            )
            return None
        return RedmineFeature(
            id=int(issue["id"]),
            subject=issue.get("subject") or "",
            description=issue.get("description") or "",
            project_id=int((issue.get("project") or {}).get("id") or 0),
        )

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
        """Creates a Feature (parent) or To-Do (child under Feature) in Redmine."""
        clean_subject = (subject or "").strip()[:255]
        clean_description = (description or "")[:60000]
        # for_parent controls tracker: Feature vs To-Do.
        # Never infer Feature just because parent_issue_id is missing.
        chosen_tracker = tracker_id or self._pick_tracker_id(
            project_id, for_parent=bool(for_parent)
        )
        if not chosen_tracker:
            kind = "Feature" if for_parent else "To-Do"
            raise RedmineAPIError(
                400,
                "issues.json",
                f"Project {project_id} has no {kind} tracker. "
                "CommitFlow will not create Support/Meeting or other wrong trackers.",
            )

        if not for_parent:
            if not parent_issue_id:
                raise RedmineAPIError(
                    400,
                    "issues.json",
                    "Refusing To-Do without a Feature parent_issue_id.",
                )
            # Critical: child under Support/Meeting becomes Support/Meeting in Redmine.
            parent = self.assert_feature_parent(int(parent_issue_id))
            if not parent:
                raise RedmineAPIError(
                    400,
                    "issues.json",
                    f"Parent #{parent_issue_id} is not a Feature tracker "
                    "(e.g. Support/Meeting). Refusing to create child To-Do under it.",
                )

        payload: Dict[str, Any] = {
            "issue": {
                "project_id": project_id,
                "subject": clean_subject,
                "description": clean_description,
                "tracker_id": int(chosen_tracker),
            }
        }
        if parent_issue_id:
            payload["issue"]["parent_issue_id"] = int(parent_issue_id)

        # Worklog To-Dos: always assign to me and mark 100% done
        if not for_parent:
            payload["issue"]["done_ratio"] = 100
            uid = self.get_current_user_id()
            if uid is not None:
                payload["issue"]["assigned_to_id"] = uid

        try:
            response = self._request("POST", "issues.json", json_data=payload)
            issue_data = response.json().get("issue", {})
            tracker_name = _issue_tracker_name(issue_data) or str(chosen_tracker)

            if for_parent:
                if not _is_feature_tracker(tracker_name):
                    raise RedmineAPIError(
                        422,
                        "issues.json",
                        f"Created issue #{issue_data.get('id')} as tracker "
                        f"{tracker_name!r}, expected Feature. Aborting.",
                    )
            elif not _is_todo_tracker(tracker_name):
                raise RedmineAPIError(
                    422,
                    "issues.json",
                    f"Created issue #{issue_data.get('id')} as tracker "
                    f"{tracker_name!r}, expected To-Do. "
                    "Will not log time on Support/Meeting.",
                )

            logger.info(
                f"Created Redmine {tracker_name} #{issue_data.get('id')} - '{clean_subject}'"
                + (f" under Feature #{parent_issue_id}" if parent_issue_id else " (Feature parent)")
            )
            return issue_data
        except RedmineAPIError as e:
            logger.error(
                f"Failed to create Redmine issue '{clean_subject}' "
                f"(tracker_id={chosen_tracker}, parent={parent_issue_id}): {e}"
            )
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
        require_todo: bool = True,
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
                    # Never reuse Support/Meeting (or other non-To-Do) for worklogs
                    if require_todo and not _is_todo_tracker(_issue_tracker_name(issue)):
                        logger.warning(
                            f"Ignoring subject match #{issue.get('id')} "
                            f"tracker={_issue_tracker_name(issue)!r} — not a To-Do"
                        )
                        continue
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
        *,
        require_todo: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Finds a To-Do by subject — prefer under Feature parent, then project-wide To-Dos only."""
        target = (subject or "").strip()
        if not target:
            return None

        try:
            if parent_issue_id:
                found = self._scan_issues_for_subject(
                    project_id,
                    target,
                    parent_issue_id=parent_issue_id,
                    require_todo=require_todo,
                )
                if found:
                    return found

            # Idempotency: already created under another Feature — To-Do only
            found = self._scan_issues_for_subject(
                project_id, target, parent_issue_id=None, require_todo=require_todo
            )
            if found:
                logger.info(
                    f"Found existing To-Do #{found.get('id')} by subject "
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
