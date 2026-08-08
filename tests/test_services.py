import pytest
from datetime import datetime
from contextlib import contextmanager
from app.models.domain import (
    Commit,
    DiscoveredRepo,
    RedmineProject,
    RedmineFeature,
)
from app.services.classifier import FeatureClassifierService
from app.services.reporting import ReportingService
from app.services.sync import SyncService
from app.services.todo_planner import TodoPlannerService, split_hours, merge_related_todos
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


def test_todo_planner_merges_down_to_max_todos():
    """16 commits under one feature, max_todos=5 → 5 merged to-dos, hours preserved."""
    from app.models.domain import ClassifiedCommit

    classified = []
    for i in range(16):
        classified.append(
            ClassifiedCommit(
                commit=Commit(
                    hash=f"hash{i}",
                    message=f"feat: work item {i}",
                    author="u",
                    repository="org/repo",
                    committed_date=datetime(2026, 8, 7, 12, 0, 0),
                    changed_files=[f"f{i}.ts"],
                    additions=10 + i,
                    deletions=2,
                ),
                project_name="Ezytix Tech",
                project_id=1,
                feature_name="Landing Page Development",
                parent_issue_id=99,
            )
        )
    planner = TodoPlannerService(daily_hour_goal=8.5, min_todos=3, max_todos=5)
    todos = planner.plan(classified, "2026-08-07")

    assert len(todos) == 5
    assert round(sum(t.hours for t in todos), 2) == 8.5
    assert all(t.parent_issue_id == 99 for t in todos)
    assert all(t.feature_name == "Landing Page Development" for t in todos)
    # Every original commit must still be represented in the merged plan
    assert sum(len(t.commits) for t in todos) == 16


def test_todo_planner_max_todos_never_merges_across_features():
    """Distinct features are never combined, even if that exceeds max_todos."""
    from app.models.domain import ClassifiedCommit

    classified = [
        ClassifiedCommit(
            commit=Commit(
                hash=f"h{i}",
                message=f"feat: item {i}",
                author="u",
                repository="org/repo",
                committed_date=datetime(2026, 8, 7, 12, 0, 0),
                changed_files=["f.ts"],
                additions=20,
                deletions=1,
            ),
            project_name="Ezytix Tech",
            project_id=1,
            feature_name=f"Feature {i}",
            parent_issue_id=100 + i,
        )
        for i in range(4)
    ]
    planner = TodoPlannerService(daily_hour_goal=8.0, min_todos=1, max_todos=2)
    todos = planner.plan(classified, "2026-08-07")

    # Cannot go below one to-do per distinct feature parent
    assert len(todos) == 4
    assert {t.feature_name for t in todos} == {f"Feature {i}" for i in range(4)}


def test_todo_planner_below_max_todos_is_unchanged():
    """max_todos above the natural count should not trigger any merging."""
    from app.models.domain import WorkTodo

    real_todos = [
        WorkTodo(
            subject=f"s{i}",
            description="",
            hours=1.0,
            project_id=1,
            project_name="P",
            feature_name="F",
            parent_issue_id=1,
            commits=[],
            is_synthetic=False,
        )
        for i in range(3)
    ]
    assert merge_related_todos(real_todos, 10) is real_todos
    assert merge_related_todos(real_todos, None) is real_todos


def test_settings_rejects_max_todos_below_min_todos():
    from app.config.settings import Settings
    import pytest as _pytest

    with _pytest.raises(Exception):
        Settings(
            REDMINE_URL="https://redmine.mock.com",
            REDMINE_API_KEY="rm_mock_key",
            MIN_TODOS=5,
            MAX_TODOS=2,
        )


def test_related_feature_match_from_commit_paths(mock_redmine_features):
    """Commit paths/messages should map to a related parent even without an exact AI label."""
    from app.services.feature_match import best_feature_for_commits, resolve_related_feature

    commit = Commit(
        hash="abc",
        message="feat(orders): add expired status handling",
        author="u",
        repository="r",
        committed_date=datetime.now(),
        changed_files=["src/pages/orders/OrderList.tsx", "src/api/orders.ts"],
    )
    # Add an Orders-like feature for relatedness
    features = list(mock_redmine_features) + [
        RedmineFeature(
            id=2004,
            subject="Orders Management",
            description="Order list, status, payments",
            project_id=101,
        )
    ]
    hit = best_feature_for_commits([commit], features)
    assert hit is not None
    assert "order" in hit[0].subject.lower()

    resolved = resolve_related_feature(
        predicted_name="General Development",
        commits=[commit],
        features=features,
        default_feature="General Development",
        confidence=40,
        confidence_threshold=80,
    )
    assert resolved == "Orders Management"


def test_resolve_related_feature_ignores_fallback_label_exact_match():
    """
    Regression test: when the AI gives up on a low-confidence commit and returns
    the configured default/fallback feature label verbatim, and that label
    happens to already exist as a real Redmine feature (e.g. a catch-all like
    'Search & Discovery Module'), it must NOT short-circuit onto that feature
    just because the name matches itself exactly. Content relatedness should
    still be checked first — otherwise every low-confidence commit collapses
    onto whichever feature the fallback label names, regardless of its content.
    """
    from app.services.feature_match import resolve_related_feature

    catch_all = RedmineFeature(
        id=1, subject="Search & Discovery Module", description="", project_id=101
    )
    payments = RedmineFeature(
        id=2, subject="Payment", description="Billing, invoices, payment gateway", project_id=101
    )
    features = [catch_all, payments]

    commit = Commit(
        hash="pay1",
        message="fix: correct invoice tax calculation in payment gateway",
        author="u",
        repository="r",
        committed_date=datetime.now(),
        changed_files=["src/payment/invoice.py", "src/payment/gateway.py"],
    )

    resolved = resolve_related_feature(
        predicted_name="Search & Discovery Module",  # AI gave up and echoed the fallback label
        commits=[commit],
        features=features,
        default_feature="Search & Discovery Module",
        confidence=10,  # low confidence — AI wasn't sure
        confidence_threshold=80,
    )
    assert resolved == "Payment"


def test_resolve_feature_parent_does_not_force_unrelated_match():
    """
    Regression test for the sync-side half of the same bug: when neither a name
    match nor a genuinely related content match exists, planning must leave the
    parent unresolved (None) rather than force-attaching to whatever existing
    Feature scores highest by accident. A missing parent is expected to be
    handled later by the normal create/confirm flow, never silently guessed.
    """
    from app.services.sync import SyncService

    unrelated_features = [
        RedmineFeature(id=1, subject="Search & Discovery Module", description="", project_id=101),
    ]
    commit = Commit(
        hash="zzz",
        message="chore: bump lockfile",
        author="u",
        repository="r",
        committed_date=datetime.now(),
        changed_files=["package-lock.json"],
    )

    class _Settings:
        default_feature = "General Development"

    # Lightweight instance stub since _resolve_feature_parent only touches
    # `self.settings.default_feature`.
    stub = object.__new__(SyncService)
    stub.settings = _Settings()
    parent, name = stub._resolve_feature_parent(unrelated_features, "General Development", commits=[commit])
    assert parent is None
    assert name == "General Development"


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
    # Low confidence but exact/near feature name still maps to the real parent
    assert result.selected_features[1].feature_name == "UI Design"


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
    mock_rm.find_feature_by_subject.side_effect = lambda project_id, subject: next(
        (f for f in mock_redmine_features if f.subject.lower() == subject.lower()),
        None,
    )
    mock_rm.ensure_feature.side_effect = lambda project_id, subject: next(
        f for f in mock_redmine_features if f.subject.lower() == subject.lower()
    )
    mock_rm.find_issue_by_subject.return_value = None
    mock_rm.create_issue.return_value = {"id": 12345}
    mock_rm.get_time_entries_for_issue_on_date.return_value = []
    mock_rm.create_time_entry.return_value = {"id": 1}
    # Direct attribute assignment (not .side_effect on the auto-attr) — unittest.mock
    # blocks auto-creating any attribute named like an assertion (assert_*) via
    # plain attribute access, which would otherwise raise on this real client method.
    mock_rm.assert_feature_parent = mocker.Mock(
        side_effect=lambda issue_id: next(
            (f for f in mock_redmine_features if f.id == issue_id), None
        )
    )
    mock_rm.ensure_todo_under_feature = mocker.Mock(return_value=None)
    mock_rm.ensure_todo_assignment = mocker.Mock(return_value=None)

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

    result = sync_service.sync_date("2026-07-06", allow_missing_parent=True)

    assert result.processed_commits_count == 1
    # 1 commit → min 3 to-dos
    assert result.todos_planned == 3
    assert len(result.created_issues) == 3
    assert result.time_entries_created == 3
    assert round(result.hours_logged, 2) == 8.0

    assert mock_rm.create_issue.call_count == 3
    assert mock_rm.create_time_entry.call_count == 3
    for call in mock_rm.create_issue.call_args_list:
        kwargs = call.kwargs
        parent_id = kwargs.get("parent_issue_id")
        if parent_id is None and len(call.args) >= 2:
            parent_id = call.args[1]
        assert parent_id, "to-dos must be created under a parent feature"

    db_repo = DatabaseRepository(db_session)
    cached = db_repo.get_cached_prediction(mock_commits[0].hash, mock_commits[0].repository)
    assert cached is not None
    assert cached.predicted_feature == "Payment"
    assert cached.confidence == 98
