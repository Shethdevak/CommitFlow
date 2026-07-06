import pytest
from datetime import datetime
from contextlib import contextmanager
from app.models.domain import Commit, RedmineFeature, FeatureMappingSelection, AIClassificationResult
from app.services.classifier import FeatureClassifierService
from app.services.reporting import ReportingService
from app.services.sync import SyncService
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
"""
    mapping_file = tmp_path / "mappings.yaml"
    mapping_file.write_text(yaml_content)

    resolver = MappingResolver(str(mapping_file))
    assert resolver.resolve_project("org/repo-a") == "Project A"
    assert resolver.resolve_project("org/repo-b") == "Project B"
    assert resolver.resolve_project("org/unknown") is None


def test_feature_classifier_resolution(mock_redmine_features):
    """Checks that predicted features are resolved using fuzzy matching and threshold safeguards."""
    # Mock AI response returning slightly off names and confidence
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
        default_feature="General Development"
    )

    commits = [
        Commit(hash="hash1", message="a", author="u", repository="r", committed_date=datetime.now(), changed_files=[]),
        Commit(hash="hash2", message="b", author="u", repository="r", committed_date=datetime.now(), changed_files=[])
    ]

    result = classifier.classify_commits(
        repository="r",
        project_name="p",
        commits=commits,
        features=mock_redmine_features,
        feedback_logs=[]
    )

    assert len(result.selected_features) == 2
    
    # Feature 1: resolved from 'Paymnts Integration' -> 'Payment' via fuzzy match
    assert result.selected_features[0].feature_name == "Payment"
    assert result.selected_features[0].confidence == 95

    # Feature 2: fallback to 'General Development' because confidence (50) is below threshold (80)
    assert result.selected_features[1].feature_name == "General Development"


def test_reporting_service(mock_commits):
    """Verifies that the markdown and HTML reports compile developer details without errors."""
    commits_by_feature = {
        "Payment": [mock_commits[0]],
        "UI Design": [mock_commits[1]]
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
    """Full workflow test verifying sync orchestrator calls cache, database, and client APIs."""
    
    # Mocking client behaviors
    mock_gh = mocker.Mock()
    mock_gh.fetch_commits.return_value = [mock_commits[0]] # Returns 1 github commit

    mock_gl = mocker.Mock()
    mock_gl.fetch_commits.return_value = []

    mock_rm = mocker.Mock()
    mock_rm.get_project.return_value = mock_redmine_project
    mock_rm.get_features.return_value = mock_redmine_features
    # Mock existing issue search to return None (no daily task created yet)
    mock_rm.search_today_issue.return_value = None
    mock_rm.create_issue.return_value = {"id": 12345}

    # Mock mappings
    mock_resolver = mocker.Mock()
    mock_resolver.mappings = {"digiflux-ezytix/be-api": "Ezytix Tech"}
    mock_resolver.resolve_project.return_value = "Ezytix Tech"

    # Mock AI response
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
        default_feature="General Development"
    )

    @contextmanager
    def mock_db_session():
        yield db_session

    # Patch database session provider to use our test in-memory db session context manager
    mocker.patch("app.services.sync.db_session", mock_db_session)
    # Patch reports file writing to prevent disk modifications
    mocker.patch("app.services.reporting.ReportingService.export_reports")

    sync_service = SyncService(
        settings=mock_settings,
        github_client=mock_gh,
        gitlab_client=mock_gl,
        redmine_client=mock_rm,
        mapping_resolver=mock_resolver,
        classifier_service=classifier
    )

    # Execute Sync for target date
    result = sync_service.sync_date("2026-07-06")

    # Assertions
    assert result.processed_commits_count == 1
    assert len(result.created_issues) == 1
    assert result.created_issues[0] == 12345
    
    # Check that it called Redmine to create a sub-task issue
    mock_rm.create_issue.assert_called_once_with(
        project_id=101,
        parent_issue_id=2001,  # Resolved ID of "Payment" Feature
        subject="Daily Development Update - 2026-07-06",
        description=mocker.ANY
    )

    # Verify that the decision was saved in SQLite Cache
    db_repo = DatabaseRepository(db_session)
    cached = db_repo.get_cached_prediction(mock_commits[0].hash, mock_commits[0].repository)
    assert cached is not None
    assert cached.predicted_feature == "Payment"
    assert cached.confidence == 98
