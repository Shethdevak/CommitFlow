import os
from datetime import datetime, time as datetime_time
from typing import Dict, List, Any, Optional
from zoneinfo import ZoneInfo
from loguru import logger
from app.config.settings import Settings
from app.models.domain import Commit, RedmineFeature, SyncResult, FeatureMappingSelection
from app.github.client import GitHubClient
from app.gitlab.client import GitLabClient
from app.redmine.client import RedmineClient
from app.mappings.resolver import MappingResolver
from app.database.repository import DatabaseRepository
from app.database.connection import db_session
from app.services.classifier import FeatureClassifierService
from app.services.reporting import ReportingService

class SyncService:
    """Orchestrates the entire Git to Redmine synchronization and classification workflow."""

    def __init__(
        self,
        settings: Settings,
        github_client: GitHubClient,
        gitlab_client: GitLabClient,
        redmine_client: RedmineClient,
        mapping_resolver: MappingResolver,
        classifier_service: FeatureClassifierService
    ):
        self.settings = settings
        self.github_client = github_client
        self.gitlab_client = gitlab_client
        self.redmine_client = redmine_client
        self.mapping_resolver = mapping_resolver
        self.classifier_service = classifier_service
        self.reporting_service = ReportingService()
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

        # Parse date 'YYYY-MM-DD'
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Local start and end times
        local_start = datetime.combine(parsed_date, datetime_time.min, tzinfo=tz)
        local_end = datetime.combine(parsed_date, datetime_time.max, tzinfo=tz)
        
        # Convert to UTC for API queries (GitHub expects UTC ISO 8601 strings)
        utc_start = local_start.astimezone(ZoneInfo("UTC"))
        utc_end = local_end.astimezone(ZoneInfo("UTC"))
        
        return utc_start, utc_end

    def _fetch_commits_for_repo(
        self,
        repository: str,
        since: datetime,
        until: datetime
    ) -> List[Commit]:
        """Attempts to fetch commits from GitHub and GitLab depending on credentials and availability."""
        commits: List[Commit] = []
        
        # Check repo config in mappings if provider is specified (default behavior)
        # We try GitHub first if token is available, otherwise GitLab.
        fetched = False
        
        if self.settings.github_token:
            try:
                commits.extend(self.github_client.fetch_commits(
                    repository=repository,
                    author_name=self._author_name,
                    since=since,
                    until=until
                ))
                fetched = True
            except Exception as e:
                logger.warning(f"Could not fetch '{repository}' from GitHub: {e}. Trying GitLab...")

        if not fetched and self.settings.gitlab_token:
            try:
                commits.extend(self.gitlab_client.fetch_commits(
                    repository=repository,
                    author_name=self._author_name,
                    since=since,
                    until=until
                ))
                fetched = True
            except Exception as e:
                logger.error(f"Could not fetch '{repository}' from GitLab: {e}")
                
        if not fetched and not self.settings.github_token and not self.settings.gitlab_token:
            logger.error("No Git credentials configured. Cannot fetch commits.")
            
        return commits

    def sync_date(self, date_str: str) -> SyncResult:
        """Runs the sync workflow for a specific date."""
        utc_since, utc_until = self._get_date_range(date_str)
        logger.info(f"Starting synchronization for {date_str} (UTC Range: {utc_since.isoformat()} to {utc_until.isoformat()})")

        sync_result = SyncResult(date=date_str, processed_commits_count=0)
        
        # 1. Load repository mappings
        repos = self.mapping_resolver.mappings.keys()
        if not repos:
            logger.warning("No repositories mapped in configs. Sync complete with 0 operations.")
            return sync_result

        # 2. Gather commits across mapped repos
        all_commits: List[Commit] = []
        for repo in repos:
            try:
                repo_commits = self._fetch_commits_for_repo(repo, utc_since, utc_until)
                all_commits.extend(repo_commits)
            except Exception as e:
                error_msg = f"Failed fetching commits for repository '{repo}': {e}"
                logger.error(error_msg)
                sync_result.errors.append(error_msg)

        if not all_commits:
            logger.info(f"No commits found for author '{self._author_name}' on {date_str}.")
            return sync_result

        sync_result.processed_commits_count = len(all_commits)

        # 3. Classify and group commits by feature
        # Dictionary of Redmine Feature Name -> List of Commits
        commits_by_feature: Dict[str, List[Commit]] = {}

        # We execute database cache checking and learning logic inside a DB session context
        with db_session() as session:
            db_repo = DatabaseRepository(session)
            
            # Step A: Separate cached commits from uncached commits
            uncached_commits_by_repo: Dict[str, List[Commit]] = {}
            
            for commit in all_commits:
                cached = db_repo.get_cached_prediction(commit.hash, commit.repository)
                if cached:
                    logger.info(f"Cache hit: Commit {commit.hash[:8]} already classified as '{cached.predicted_feature}'")
                    commits_by_feature.setdefault(cached.predicted_feature, []).append(commit)
                    sync_result.cached_commits_count += 1
                else:
                    uncached_commits_by_repo.setdefault(commit.repository, []).append(commit)

            # Step B: Classify uncached commits using AI on a per-repository basis
            for repo, commits in uncached_commits_by_repo.items():
                project_name = self.mapping_resolver.resolve_project(repo)
                if not project_name:
                    logger.warning(f"No Redmine project mapped for '{repo}'. Skipping AI classification.")
                    sync_result.errors.append(f"Skipped repository '{repo}' due to missing project mapping.")
                    continue

                # Fetch project details from Redmine
                project = self.redmine_client.get_project(project_name)
                if not project:
                    error_msg = f"Redmine project '{project_name}' not found on server. Skipping repository '{repo}'."
                    logger.error(error_msg)
                    sync_result.errors.append(error_msg)
                    continue

                # Retrieve available Redmine Features (parent issues)
                features = self.redmine_client.get_features(project.id)
                feedback_logs = db_repo.get_feedback_logs()

                # Call AI classifier service
                classification_result = self.classifier_service.classify_commits(
                    repository=repo,
                    project_name=project.name,
                    commits=commits,
                    features=features,
                    feedback_logs=feedback_logs
                )

                # Process AI results, save to cache and build feature map
                for selection in classification_result.selected_features:
                    # Find all full Commit objects matching the hashes
                    matched_commits = [c for c in commits if c.hash in selection.commits]
                    
                    for commit in matched_commits:
                        # Save decision in local cache
                        db_repo.save_cache_entry(
                            commit_hash=commit.hash,
                            repository=commit.repository,
                            predicted_feature=selection.feature_name,
                            confidence=selection.confidence,
                            reason=selection.reason,
                            provider=self.settings.ai_provider
                        )
                        commits_by_feature.setdefault(selection.feature_name, []).append(commit)

        # 4. Create or Update daily work log issues in Redmine
        # Group features by Redmine Project to coordinate Redmine queries
        for feature_name, commits in commits_by_feature.items():
            if not commits:
                continue

            # Find the Redmine project mapped to these commits
            # Assume first commit's repo mapping is representative
            repo = commits[0].repository
            project_name = self.mapping_resolver.resolve_project(repo)
            if not project_name:
                continue

            project = self.redmine_client.get_project(project_name)
            if not project:
                continue

            # Retrieve features list from Redmine to resolve target parent issue ID
            features = self.redmine_client.get_features(project.id)
            target_feature = next((f for f in features if f.subject == feature_name), None)
            
            parent_issue_id = None
            if target_feature:
                parent_issue_id = target_feature.id
            elif feature_name != self.settings.default_feature:
                # If predicted feature is not found, try to resolve default feature ID
                default_feat = next((f for f in features if f.subject == self.settings.default_feature), None)
                if default_feat:
                    parent_issue_id = default_feat.id
                    logger.warning(f"Feature '{feature_name}' not found in Redmine. Falling back to default feature ID #{parent_issue_id}.")
            
            # Formatting descriptions
            subject = f"Daily Development Update - {date_str}"
            
            # Generate body summary
            body = self._format_issue_description(commits)

            # Check if work log issue already exists under this feature for today
            # If no parent_issue_id found (meaning we map to default feature which doesn't exist either),
            # we will search without parent_id (or root level issue).
            existing_issue = None
            if parent_issue_id:
                existing_issue = self.redmine_client.search_today_issue(project.id, parent_issue_id, date_str)

            if existing_issue:
                # Issue exists, append today's commits as a note to avoid duplicate issues
                logger.info(f"Work log already exists under Feature '{feature_name}' (Issue #{existing_issue['id']}). Appending notes...")
                note = self._format_issue_note(commits)
                try:
                    self.redmine_client.add_note(existing_issue["id"], note)
                    sync_result.updated_issues.append(existing_issue["id"])
                except Exception as e:
                    error_msg = f"Failed to append note to issue #{existing_issue['id']}: {e}"
                    logger.error(error_msg)
                    sync_result.errors.append(error_msg)
            else:
                # Issue does not exist, create it as a child task
                logger.info(f"Creating new daily work log under Feature '{feature_name}'...")
                try:
                    new_issue = self.redmine_client.create_issue(
                        project_id=project.id,
                        parent_issue_id=parent_issue_id,
                        subject=subject,
                        description=body
                    )
                    sync_result.created_issues.append(new_issue["id"])
                except Exception as e:
                    error_msg = f"Failed to create new daily work log under feature '{feature_name}': {e}"
                    logger.error(error_msg)
                    sync_result.errors.append(error_msg)

        # 5. Generate and export reports
        try:
            self.reporting_service.export_reports(commits_by_feature, date_str)
            logger.info("Daily summaries successfully exported (Markdown, HTML, CSV).")
        except Exception as e:
            logger.error(f"Error exporting reports: {e}")
            sync_result.errors.append(f"Failed exporting reports: {e}")

        logger.info(f"Synchronization complete. Processed {sync_result.processed_commits_count} commits, created {len(sync_result.created_issues)} issues, updated {len(sync_result.updated_issues)} issues.")
        return sync_result

    def _format_issue_description(self, commits: List[Commit]) -> str:
        """Formats the detailed work log description for the child issue."""
        desc = ""
        # Group by repository
        repo_groups: Dict[str, List[Commit]] = {}
        for c in commits:
            repo_groups.setdefault(c.repository, []).append(c)

        for repo, r_commits in repo_groups.items():
            desc += f"Repository:\n{repo}\n\n"
            desc += "Commits\n"
            for c in r_commits:
                desc += f"• {c.message}\n"
            desc += "\n"
            
            # Commit metadata table representation
            desc += "| Commit Hash | Commit URL | Commit Time |\n"
            desc += "| :--- | :--- | :--- |\n"
            for c in r_commits:
                short_hash = c.hash[:8]
                time_str = c.committed_date.strftime("%H:%M:%S")
                url_str = c.url if c.url else "N/A"
                desc += f"| {short_hash} | {url_str} | {time_str} |\n"
            desc += "\n"
            
        return desc.strip()

    def _format_issue_note(self, commits: List[Commit]) -> str:
        """Formats a journal note when appending commits to an existing issue."""
        note = "Added new development updates:\n\n"
        repo_groups: Dict[str, List[Commit]] = {}
        for c in commits:
            repo_groups.setdefault(c.repository, []).append(c)

        for repo, r_commits in repo_groups.items():
            note += f"Repository: {repo}\n"
            for c in r_commits:
                short_hash = c.hash[:8]
                time_str = c.committed_date.strftime("%H:%M:%S")
                note += f"- {c.message} ({short_hash} at {time_str})\n"
            note += "\n"
        return note.strip()
