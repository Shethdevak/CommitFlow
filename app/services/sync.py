from datetime import datetime, time as datetime_time
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo
from loguru import logger
from app.config.settings import Settings
from app.models.domain import (
    Commit,
    DiscoveredRepo,
    ClassifiedCommit,
    SyncResult,
    WorkTodo,
)
from app.github.client import GitHubClient
from app.gitlab.client import GitLabClient
from app.redmine.client import RedmineClient
from app.mappings.resolver import MappingResolver
from app.database.repository import DatabaseRepository
from app.database.connection import db_session
from app.services.classifier import FeatureClassifierService
from app.services.reporting import ReportingService
from app.services.todo_planner import TodoPlannerService


class SyncService:
    """Orchestrates Git discovery, AI classification, to-do creation, and time logging."""

    def __init__(
        self,
        settings: Settings,
        github_client: GitHubClient,
        gitlab_client: GitLabClient,
        redmine_client: RedmineClient,
        mapping_resolver: MappingResolver,
        classifier_service: FeatureClassifierService,
    ):
        self.settings = settings
        self.github_client = github_client
        self.gitlab_client = gitlab_client
        self.redmine_client = redmine_client
        self.mapping_resolver = mapping_resolver
        self.classifier_service = classifier_service
        self.reporting_service = ReportingService()
        self.todo_planner = TodoPlannerService(
            daily_hour_goal=settings.daily_hour_goal,
            min_todos=settings.min_todos,
        )
        self._author_name = self._resolve_author_name()

    def _resolve_author_name(self) -> str:
        """Returns AUTHOR_NAME from settings, or auto-detects it from the Git provider API."""
        if self.settings.author_name:
            logger.info(f"Using configured author name: '{self.settings.author_name}'")
            return self.settings.author_name

        logger.info("AUTHOR_NAME not set — auto-detecting from Git provider token...")

        if self.settings.github_token:
            name = self.github_client.get_authenticated_user()
            if name:
                logger.info(f"Auto-detected author name from GitHub: '{name}'")
                return name

        if self.settings.gitlab_token:
            name = self.gitlab_client.get_authenticated_user()
            if name:
                logger.info(f"Auto-detected author name from GitLab: '{name}'")
                return name

        raise ValueError(
            "Could not determine author name. "
            "Either set AUTHOR_NAME in .env or ensure GITHUB_TOKEN / GITLAB_TOKEN is valid."
        )

    def _get_date_range(self, date_str: str) -> tuple[datetime, datetime]:
        """Calculates timezone-aware start and end datetimes in UTC for the query."""
        try:
            tz = ZoneInfo(self.settings.timezone)
        except Exception as e:
            logger.warning(f"Invalid timezone '{self.settings.timezone}' ({e}). Falling back to UTC.")
            tz = ZoneInfo("UTC")

        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        local_start = datetime.combine(parsed_date, datetime_time.min, tzinfo=tz)
        local_end = datetime.combine(parsed_date, datetime_time.max, tzinfo=tz)
        return local_start.astimezone(ZoneInfo("UTC")), local_end.astimezone(ZoneInfo("UTC"))

    def _discover_repos(self) -> List[DiscoveredRepo]:
        """Fetches repositories from GitHub and/or GitLab."""
        discovered: List[DiscoveredRepo] = []
        seen: set[str] = set()

        if self.settings.github_token:
            try:
                for repo in self.github_client.list_repos():
                    key = f"github:{repo.full_name.lower()}"
                    if key not in seen:
                        seen.add(key)
                        discovered.append(repo)
            except Exception as e:
                logger.error(f"GitHub repo discovery failed: {e}")

        if self.settings.gitlab_token:
            try:
                for repo in self.gitlab_client.list_repos():
                    key = f"gitlab:{repo.full_name.lower()}"
                    if key not in seen:
                        seen.add(key)
                        discovered.append(repo)
            except Exception as e:
                logger.error(f"GitLab repo discovery failed: {e}")

        # Also include YAML-only overrides that may not appear in discovery
        for repo_key in self.mapping_resolver.mappings.keys():
            provider = self.mapping_resolver.providers.get(repo_key)
            # Prefer gitlab if configured (common for Digiflux), else github
            if not provider:
                if self.settings.gitlab_token and not any(
                    r.full_name.lower() == repo_key for r in discovered
                ):
                    provider = "gitlab" if self.settings.gitlab_token else "github"
                elif self.settings.github_token:
                    provider = "github"
                else:
                    continue
            if not any(r.full_name.lower() == repo_key and r.provider == provider for r in discovered):
                # Avoid duplicate same full_name+provider
                if not any(r.full_name.lower() == repo_key for r in discovered):
                    discovered.append(
                        DiscoveredRepo(
                            full_name=repo_key,
                            name=repo_key.split("/")[-1],
                            provider=provider if provider in ("github", "gitlab") else "gitlab",
                        )
                    )

        logger.info(f"Total discovered repositories: {len(discovered)}")
        return discovered

    def _fetch_commits_for_repo(
        self,
        repository: str,
        provider: str,
        since: datetime,
        until: datetime,
    ) -> List[Commit]:
        """Fetches commits from the specified provider only."""
        if provider == "github":
            if not self.settings.github_token:
                logger.warning(f"No GitHub token; skipping '{repository}'.")
                return []
            return self.github_client.fetch_commits(
                repository=repository,
                author_name=self._author_name,
                since=since,
                until=until,
            )

        if provider == "gitlab":
            if not self.settings.gitlab_token:
                logger.warning(f"No GitLab token; skipping '{repository}'.")
                return []
            return self.gitlab_client.fetch_commits(
                repository=repository,
                author_name=self._author_name,
                since=since,
                until=until,
            )

        logger.error(f"Unknown provider '{provider}' for repository '{repository}'.")
        return []

    def sync_date(self, date_str: str, dry_run: bool = False) -> SyncResult:
        """Runs the sync workflow for a specific date.

        When dry_run=True, fetches/classifies/plans but does not write to Redmine.
        """
        utc_since, utc_until = self._get_date_range(date_str)
        logger.info(
            f"Starting synchronization for {date_str} "
            f"(UTC Range: {utc_since.isoformat()} to {utc_until.isoformat()})"
            + (" [DRY RUN]" if dry_run else "")
        )

        sync_result = SyncResult(date=date_str, processed_commits_count=0, dry_run=dry_run)

        # 1. Discover repos from both providers
        discovered = self._discover_repos()
        if not discovered:
            logger.warning("No repositories discovered. Sync complete with 0 operations.")
            return sync_result

        # 2. Load Redmine projects for fuzzy matching
        try:
            redmine_projects = self.redmine_client.get_projects()
        except Exception as e:
            error_msg = f"Failed to load Redmine projects: {e}"
            logger.error(error_msg)
            sync_result.errors.append(error_msg)
            return sync_result

        project_by_name = {p.name: p for p in redmine_projects}

        # 3. Resolve each repo → Redmine project, fetch commits from the correct provider
        all_commits: List[Commit] = []
        repo_project_map: Dict[str, str] = {}  # repo full_name -> project name

        for repo in discovered:
            project_name = self.mapping_resolver.resolve_project(
                repository=repo.full_name,
                redmine_projects=redmine_projects,
                repo_short_name=repo.name,
            )
            if not project_name:
                sync_result.unmapped_repos.append(f"{repo.provider}:{repo.full_name}")
                continue

            if project_name not in project_by_name:
                # Override may use a name that still needs lookup
                matched = self.redmine_client.get_project(project_name)
                if matched:
                    project_by_name[matched.name] = matched
                    project_name = matched.name
                else:
                    sync_result.errors.append(
                        f"Redmine project '{project_name}' not found for repo '{repo.full_name}'."
                    )
                    continue

            provider = self.mapping_resolver.resolve_provider(repo.full_name, repo) or repo.provider
            repo_project_map[repo.full_name] = project_name

            try:
                commits = self._fetch_commits_for_repo(
                    repository=repo.full_name,
                    provider=provider,
                    since=utc_since,
                    until=utc_until,
                )
                all_commits.extend(commits)
            except Exception as e:
                error_msg = f"Failed fetching commits for '{repo.full_name}' ({provider}): {e}"
                logger.error(error_msg)
                sync_result.errors.append(error_msg)

        if not all_commits:
            logger.info(f"No commits found for author '{self._author_name}' on {date_str}.")
            if sync_result.unmapped_repos:
                logger.warning(f"Unmapped repos: {sync_result.unmapped_repos}")
            return sync_result

        sync_result.processed_commits_count = len(all_commits)

        # 4. Classify commits → features (with cache)
        classified: List[ClassifiedCommit] = []

        with db_session() as session:
            db_repo = DatabaseRepository(session)

            uncached_by_repo: Dict[str, List[Commit]] = {}
            cached_feature_by_hash: Dict[Tuple[str, str], str] = {}

            for commit in all_commits:
                cached = db_repo.get_cached_prediction(commit.hash, commit.repository)
                if cached:
                    logger.info(
                        f"Cache hit: Commit {commit.hash[:8]} → '{cached.predicted_feature}'"
                    )
                    cached_feature_by_hash[(commit.hash, commit.repository)] = cached.predicted_feature
                    sync_result.cached_commits_count += 1
                else:
                    uncached_by_repo.setdefault(commit.repository, []).append(commit)

            # Resolve features for cached commits
            features_cache: Dict[int, list] = {}

            def _features_for_project(project_id: int):
                if project_id not in features_cache:
                    features_cache[project_id] = self.redmine_client.get_features(project_id)
                return features_cache[project_id]

            for commit in all_commits:
                project_name = repo_project_map.get(commit.repository)
                if not project_name:
                    continue
                project = project_by_name.get(project_name)
                if not project:
                    continue

                feature_name = cached_feature_by_hash.get((commit.hash, commit.repository))
                if feature_name:
                    features = _features_for_project(project.id)
                    parent = next((f for f in features if f.subject == feature_name), None)
                    if not parent and feature_name != self.settings.default_feature:
                        parent = next(
                            (f for f in features if f.subject == self.settings.default_feature),
                            None,
                        )
                        if parent:
                            feature_name = parent.subject
                    classified.append(
                        ClassifiedCommit(
                            commit=commit,
                            project_name=project.name,
                            project_id=project.id,
                            feature_name=feature_name,
                            parent_issue_id=parent.id if parent else None,
                        )
                    )

            # AI-classify uncached commits per repository
            feedback_logs = db_repo.get_feedback_logs()
            for repo, commits in uncached_by_repo.items():
                project_name = repo_project_map.get(repo)
                if not project_name:
                    continue
                project = project_by_name.get(project_name)
                if not project:
                    continue

                features = _features_for_project(project.id)
                classification_result = self.classifier_service.classify_commits(
                    repository=repo,
                    project_name=project.name,
                    commits=commits,
                    features=features,
                    feedback_logs=feedback_logs,
                )

                hash_to_feature: Dict[str, str] = {}
                for selection in classification_result.selected_features:
                    for h in selection.commits:
                        hash_to_feature[h] = selection.feature_name
                        matched = [c for c in commits if c.hash == h]
                        for commit in matched:
                            db_repo.save_cache_entry(
                                commit_hash=commit.hash,
                                repository=commit.repository,
                                predicted_feature=selection.feature_name,
                                confidence=selection.confidence,
                                reason=selection.reason,
                                provider=self.settings.ai_provider,
                            )

                for commit in commits:
                    feature_name = hash_to_feature.get(commit.hash, self.settings.default_feature)
                    parent = next((f for f in features if f.subject == feature_name), None)
                    if not parent and feature_name != self.settings.default_feature:
                        parent = next(
                            (f for f in features if f.subject == self.settings.default_feature),
                            None,
                        )
                        if parent:
                            feature_name = parent.subject
                    classified.append(
                        ClassifiedCommit(
                            commit=commit,
                            project_name=project.name,
                            project_id=project.id,
                            feature_name=feature_name,
                            parent_issue_id=parent.id if parent else None,
                        )
                    )

        if not classified:
            logger.info("No commits could be classified into Redmine projects/features.")
            return sync_result

        # 5. Plan to-dos + distribute 8h across the day
        todos = self.todo_planner.plan(classified, date_str)
        sync_result.todos_planned = len(todos)
        sync_result.planned_todos = todos

        # 6. Create/update Redmine issues and log time entries (skipped in dry-run)
        if dry_run:
            sync_result.hours_logged = round(sum(t.hours for t in todos), 2)
            logger.info(
                f"DRY RUN: skipping Redmine writes. Would create/update "
                f"{len(todos)} to-do(s) totaling {sync_result.hours_logged}h."
            )
        else:
            for todo in todos:
                self._upsert_todo_and_time(todo, date_str, sync_result)

        # 7. Export reports (group by feature for compatibility)
        commits_by_feature: Dict[str, List[Commit]] = {}
        for item in classified:
            commits_by_feature.setdefault(item.feature_name, []).append(item.commit)

        if not dry_run:
            try:
                self.reporting_service.export_reports(commits_by_feature, date_str)
                logger.info("Daily summaries successfully exported (Markdown, HTML, CSV).")
            except Exception as e:
                logger.error(f"Error exporting reports: {e}")
                sync_result.errors.append(f"Failed exporting reports: {e}")
        else:
            logger.info("DRY RUN: skipping report export.")

        logger.info(
            f"Synchronization complete. Commits={sync_result.processed_commits_count}, "
            f"todos={sync_result.todos_planned}, created={len(sync_result.created_issues)}, "
            f"updated={len(sync_result.updated_issues)}, "
            f"hours={sync_result.hours_logged}, time_entries={sync_result.time_entries_created}."
        )
        return sync_result

    def _upsert_todo_and_time(self, todo: WorkTodo, date_str: str, sync_result: SyncResult) -> None:
        """Creates or reuses a to-do issue and logs hours if not already logged for the day."""
        subject = todo.subject
        # Prefix date so re-runs can find the same daily to-do
        dated_subject = f"[{date_str}] {subject}"[:255]

        try:
            existing = self.redmine_client.find_issue_by_subject(
                project_id=todo.project_id,
                subject=dated_subject,
                parent_issue_id=todo.parent_issue_id,
            )

            if existing:
                issue_id = existing["id"]
                logger.info(f"Reusing existing to-do #{issue_id}: {dated_subject}")
                sync_result.updated_issues.append(issue_id)
            else:
                new_issue = self.redmine_client.create_issue(
                    project_id=todo.project_id,
                    parent_issue_id=todo.parent_issue_id,
                    subject=dated_subject,
                    description=todo.description,
                )
                issue_id = new_issue["id"]
                sync_result.created_issues.append(issue_id)

            # Avoid duplicate time entries on re-sync
            existing_entries = self.redmine_client.get_time_entries_for_issue_on_date(
                issue_id, date_str
            )
            already = sum(float(e.get("hours", 0)) for e in existing_entries)
            if already >= todo.hours:
                logger.info(
                    f"Issue #{issue_id} already has {already}h on {date_str}; skipping time log."
                )
                sync_result.hours_logged += already
                return

            hours_to_log = round(todo.hours - already, 2)
            if hours_to_log > 0:
                self.redmine_client.create_time_entry(
                    issue_id=issue_id,
                    hours=hours_to_log,
                    spent_on=date_str,
                    comments=todo.subject[:200],
                )
                sync_result.time_entries_created += 1
                sync_result.hours_logged += hours_to_log + already
            else:
                sync_result.hours_logged += already

        except Exception as e:
            error_msg = f"Failed to upsert to-do '{dated_subject}': {e}"
            logger.error(error_msg)
            sync_result.errors.append(error_msg)
