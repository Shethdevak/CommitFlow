import pytest
from datetime import datetime
from contextlib import contextmanager
from app.models.domain import (
    Commit,
    DiscoveredRepo,
    RedmineProject,
)
from app.services.classifier import FeatureClassifierService
from app.services.reporting import ReportingService
from app.services.sync import SyncService
from app.services.todo_planner import TodoPlannerService, split_hours
from app.mappings.resolver import MappingResolver
from app.database.repository import DatabaseRepository
from app.ai.provider import AIProvider


class MockAIProvider(AIProvider):
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.prompt_received = ""

    def classify(self, prompt: str) -> str:
        self.prompt_received = prompt
        return self.response_text


def test_mapping_resolver(tmp_path):
    """Verifies that the YAML mapping resolver parses structures correctly."""
    yaml_content = """
repositories:
  org/repo-a: Project A
  org/repo-b:
    redmine_project: Project B
    provider: gitlab
"""
    mapping_file = tmp_path / "mappings.yaml"
    mapping_file.write_text(yaml_content)

    resolver = MappingResolver(str(mapping_file))
    assert resolver.resolve_project("org/repo-a") == "Project A"
    assert resolver.resolve_project("org/repo-b") == "Project B"
    assert resolver.resolve_project("org/unknown") is None
    assert resolver.resolve_provider("org/repo-b") == "gitlab"


def test_mapping_resolver_fuzzy_match(tmp_path):
    """Fuzzy-matches repo short names to Redmine project names."""
    mapping_file = tmp_path / "mappings.yaml"
    mapping_file.write_text("repositories: {}")

    resolver = MappingResolver(str(mapping_file), match_threshold=70)
    projects = [
        RedmineProject(id=1, name="Mixa Shop", identifier="mixa", description=""),
        RedmineProject(id=2, name="Digiflux AssetTrack", identifier="asset", description=""),
    ]
    assert resolver.resolve_project(
        "digiflux-devs/mixa-shop",
        redmine_projects=projects,
        repo_short_name="mixa-shop",
    ) == "Mixa Shop"
    assert resolver.resolve_project(
        "digiflux-devs/Digiflux-AssetTrack-BE",
        redmine_projects=projects,
        repo_short_name="Digiflux-AssetTrack-BE",
    ) == "Digiflux AssetTrack"


def test_split_hours_sums_to_goal():
    assert sum(split_hours(8, 3)) == 8
    assert sum(split_hours(8, 6)) == 8
    assert len(split_hours(8, 6)) == 6
    assert all(h > 0 for h in split_hours(8, 3))


def test_weighted_hours_favor_large_features():
    """Big feat gets more hours than a tiny quick fix; total still 8h."""
    from app.models.domain import ClassifiedCommit
    from app.services.todo_planner import score_commit, allocate_hours_by_weights

    small = Commit(
        hash="s1",
        message="fix: typo in label",
        author="u",
        repository="org/repo",
        committed_date=datetime(2026, 7, 16, 10, 0, 0),
        changed_files=["a.tsx"],
        additions=2,
        deletions=1,
    )
    big = Commit(
        hash="b1",
        message="feat: implement event visibility management",
        author="u",
        repository="org/repo",
        committed_date=datetime(2026, 7, 16, 12, 0, 0),
        changed_files=[f"f{i}.tsx" for i in range(12)],
        additions=280,
        deletions=40,
    )
    medium = Commit(
        hash="m1",
        message="feat: enhance venue map preview",
        author="u",
        repository="org/repo",
        committed_date=datetime(2026, 7, 16, 14, 0, 0),
        changed_files=["map.tsx", "preview.tsx", "types.ts"],
        additions=90,
        deletions=20,
    )

    assert score_commit(big) > score_commit(medium) > score_commit(small)

    hours = allocate_hours_by_weights(8.0, [score_commit(small), score_commit(big), score_commit(medium)])
    assert round(sum(hours), 2) == 8.0
    assert hours[1] > hours[0]  # big > small
    assert hours[1] >= hours[2]  # big >= medium
    assert hours[0] <= 1.5  # quick fix stays modest


def test_todo_planner_pads_below_min():
    """1 commit → 3 to-dos totaling 8h."""
    from app.models.domain import ClassifiedCommit

    commit = Commit(
        hash="abc123",
        message="Fix login",
        author="u",
        repository="org/repo",
        committed_date=datetime(2026, 7, 10, 12, 0, 0),
        changed_files=["login.ts"],
        additions=15,
        deletions=3,
    )
    classified = [
        ClassifiedCommit(
            commit=commit,
            project_name="Proj",
            project_id=1,
            feature_name="Payment",
            parent_issue_id=10,
        )
    ]
    planner = TodoPlannerService(daily_hour_goal=8.0, min_todos=3)
    todos = planner.plan(classified, "2026-07-10")
    assert len(todos) == 3
    assert round(sum(t.hours for t in todos), 2) == 8.0
    assert sum(1 for t in todos if t.is_synthetic) == 2
    # Main commit should get the largest share
    assert todos[0].hours >= todos[1].hours
    assert todos[0].hours >= todos[2].hours


def test_todo_planner_one_per_commit_when_many():
    """6 commits → 6 to-dos totaling 8h with unequal effort weights."""
    from app.models.domain import ClassifiedCommit

    classified = []
    for i in range(6):
        classified.append(
            ClassifiedCommit(
                commit=Commit(
                    hash=f"hash{i}",
                    message=f"feat: work item {i}" if i < 2 else f"fix: quick tweak {i}",
                    author="u",
                    repository="org/repo",
                    committed_date=datetime(2026, 7, 10, 12, 0, 0),
                    changed_files=[f"f{j}.ts" for j in range(1 + i * 2)],
                    additions=10 + i * 40,
                    deletions=2 + i,
                ),
                project_name="Proj",
                project_id=1,
                feature_name="Payment",
                parent_issue_id=10,
            )
        )
    planner = TodoPlannerService(daily_hour_goal=8.0, min_todos=3)
    todos = planner.plan(classified, "2026-07-10")
    assert len(todos) == 6
    assert round(sum(t.hours for t in todos), 2) == 8.0
    assert all(not t.is_synthetic for t in todos)
    # Not all equal anymore
    assert len(set(t.hours for t in todos)) > 1


def test_feature_classifier_resolution(mock_redmine_features):
    """Checks that predicted features are resolved using fuzzy matching and threshold safeguards."""
    response_json = """{
        "selected_features": [
            {
                "feature_name": "Paymnts Integration",
                "confidence": 95,
                "commits": ["hash1"],
                "reason": "payment file modified"
            },
            {
                "feature_name": "UI Design",
                "confidence": 50,
                "commits": ["hash2"],
                "reason": "low confidence change"
            }
        ]
    }"""

    mock_provider = MockAIProvider(response_json)
    classifier = FeatureClassifierService(
        ai_provider=mock_provider,
        confidence_threshold=80,
        default_feature="General Development",
    )

    commits = [
        Commit(hash="hash1", message="a", author="u", repository="r", committed_date=datetime.now(), changed_files=[]),
        Commit(hash="hash2", message="b", author="u", repository="r", committed_date=datetime.now(), changed_files=[]),
    ]

    result = classifier.classify_commits(
        repository="r",
        project_name="p",
        commits=commits,
        features=mock_redmine_features,
        feedback_logs=[],
    )

    assert len(result.selected_features) == 2
    assert result.selected_features[0].feature_name == "Payment"
    assert result.selected_features[0].confidence == 95
    assert result.selected_features[1].feature_name == "General Development"


def test_reporting_service(mock_commits):
    """Verifies that the markdown and HTML reports compile developer details without errors."""
    commits_by_feature = {
        "Payment": [mock_commits[0]],
        "UI Design": [mock_commits[1]],
    }

    md_report = ReportingService.generate_markdown(commits_by_feature, "2026-07-06")
    assert "# Daily Development Update - 2026-07-06" in md_report
    assert "Feature: Payment" in md_report
    assert "Fixed invoice calculation issue" in md_report

    html_report = ReportingService.generate_html(commits_by_feature, "2026-07-06")
    assert "Daily Work Summary - 2026-07-06" in html_report
    assert "dashboard layout" in html_report

    csv_report = ReportingService.generate_csv(commits_by_feature, "2026-07-06")
    assert "Date,Feature,Repository" in csv_report


def test_sync_service_execution(mocker, mock_settings, mock_commits, mock_redmine_project, mock_redmine_features, db_session):
    """Full workflow: discover → classify → plan to-dos → create issues + time entries."""

    mock_gh = mocker.Mock()
    mock_gh.list_repos.return_value = [
        DiscoveredRepo(full_name="digiflux-ezytix/be-api", name="be-api", provider="github")
    ]
    mock_gh.fetch_commits.return_value = [mock_commits[0]]

    mock_gl = mocker.Mock()
    mock_gl.list_repos.return_value = []
    mock_gl.fetch_commits.return_value = []

    mock_rm = mocker.Mock()
    mock_rm.get_projects.return_value = [mock_redmine_project]
    mock_rm.get_project.return_value = mock_redmine_project
    mock_rm.get_features.return_value = mock_redmine_features
    mock_rm.find_issue_by_subject.return_value = None
    mock_rm.create_issue.return_value = {"id": 12345}
    mock_rm.get_time_entries_for_issue_on_date.return_value = []
    mock_rm.create_time_entry.return_value = {"id": 1}

    mock_resolver = mocker.Mock()
    mock_resolver.mappings = {"digiflux-ezytix/be-api": "Ezytix Tech"}
    mock_resolver.providers = {"digiflux-ezytix/be-api": "github"}
    mock_resolver.resolve_project.return_value = "Ezytix Tech"
    mock_resolver.resolve_provider.return_value = "github"

    ai_response = """{
        "selected_features": [
            {
                "feature_name": "Payment",
                "confidence": 98,
                "commits": ["c1b2a3d4e5f6g7h8"],
                "reason": "Tax calculations updated"
            }
        ]
    }"""
    mock_provider = MockAIProvider(ai_response)
    classifier = FeatureClassifierService(
        ai_provider=mock_provider,
        confidence_threshold=80,
        default_feature="General Development",
    )

    @contextmanager
    def mock_db_session():
        yield db_session

    mocker.patch("app.services.sync.db_session", mock_db_session)
    mocker.patch("app.services.reporting.ReportingService.export_reports")

    sync_service = SyncService(
        settings=mock_settings,
        github_client=mock_gh,
        gitlab_client=mock_gl,
        redmine_client=mock_rm,
        mapping_resolver=mock_resolver,
        classifier_service=classifier,
    )

    result = sync_service.sync_date("2026-07-06")

    assert result.processed_commits_count == 1
    # 1 commit → min 3 to-dos
    assert result.todos_planned == 3
    assert len(result.created_issues) == 3
    assert result.time_entries_created == 3
    assert round(result.hours_logged, 2) == 8.0

    assert mock_rm.create_issue.call_count == 3
    assert mock_rm.create_time_entry.call_count == 3

    db_repo = DatabaseRepository(db_session)
    cached = db_repo.get_cached_prediction(mock_commits[0].hash, mock_commits[0].repository)
    assert cached is not None
    assert cached.predicted_feature == "Payment"
    assert cached.confidence == 98
