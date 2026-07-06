import pytest
from datetime import datetime
from app.github.client import GitHubClient
from app.gitlab.client import GitLabClient
from app.redmine.client import RedmineClient

def test_github_client_fetch_commits(mocker):
    """Verifies that the GitHubClient constructs endpoints and parses commits correctly."""
    github = GitHubClient(token="test_token")
    
    # Mocking API calls
    mock_commits_response = mocker.Mock()
    mock_commits_response.headers = {"X-RateLimit-Remaining": "100"}
    mock_commits_response.json.return_value = [
        {
            "sha": "abc12345",
            "commit": {
                "message": "Update database index\nDetail note",
                "author": {"name": "Test Author", "date": "2026-07-06T12:00:00Z"},
                "committer": {"name": "Test Author", "date": "2026-07-06T12:00:00Z"}
            },
            "html_url": "https://github.com/org/repo/commit/abc12345"
        }
    ]
    
    mock_detail_response = mocker.Mock()
    mock_detail_response.headers = {}
    mock_detail_response.json.return_value = {
        "files": [{"filename": "db/schema.sql"}],
        "stats": {"additions": 5, "deletions": 1}
    }
    
    # Patch request calls
    mock_req = mocker.patch("requests.request", side_effect=[mock_commits_response, mock_detail_response])

    since = datetime(2026, 7, 6, 0, 0, 0)
    until = datetime(2026, 7, 6, 23, 59, 59)
    
    commits = github.fetch_commits("org/repo", "Test Author", since, until)
    
    assert len(commits) == 1
    commit = commits[0]
    assert commit.hash == "abc12345"
    assert commit.message == "Update database index"
    assert commit.description == "Detail note"
    assert commit.changed_files == ["db/schema.sql"]
    assert commit.additions == 5
    assert commit.deletions == 1
    
    # Confirm endpoint mapping
    mock_req.assert_any_call(
        "GET", "https://api.github.com/repos/org/repo/commits",
        headers=mocker.ANY, params=mocker.ANY, timeout=mocker.ANY
    )


def test_gitlab_client_fetch_commits(mocker):
    """Verifies that the GitLabClient builds proper API parameters and processes response diffs."""
    gitlab = GitLabClient(token="test_token", base_url="https://gitlab.com")
    
    mock_commits_response = mocker.Mock()
    mock_commits_response.json.return_value = [
        {
            "id": "def67890",
            "message": "Refactored checkout flow",
            "author_name": "Test Author",
            "author_email": "author@test.com",
            "created_at": "2026-07-06T14:00:00.000Z",
            "stats": {"additions": 20, "deletions": 4}
        }
    ]
    
    mock_diff_response = mocker.Mock()
    mock_diff_response.json.return_value = [
        {"new_path": "src/checkout.py", "old_path": "src/checkout.py"}
    ]
    
    mocker.patch("requests.request", side_effect=[mock_commits_response, mock_diff_response])
    
    since = datetime(2026, 7, 6, 0, 0, 0)
    until = datetime(2026, 7, 6, 23, 59, 59)
    
    commits = gitlab.fetch_commits("org/repo", "Test Author", since, until)
    
    assert len(commits) == 1
    commit = commits[0]
    assert commit.hash == "def67890"
    assert commit.message == "Refactored checkout flow"
    assert commit.changed_files == ["src/checkout.py"]


def test_redmine_client_get_project(mocker):
    """Verifies project discovery and matching logic in RedmineClient."""
    redmine = RedmineClient(base_url="https://redmine.test", api_key="api_key")
    
    mock_proj_response = mocker.Mock()
    mock_proj_response.json.return_value = {
        "projects": [
            {"id": 1, "name": "Ezytix Tech", "identifier": "ezytix-tech", "description": ""},
            {"id": 2, "name": "ERP System", "identifier": "erp-system", "description": ""}
        ]
    }
    mocker.patch("requests.request", return_value=mock_proj_response)
    
    # Check by identifier
    project = redmine.get_project("ezytix-tech")
    assert project is not None
    assert project.id == 1
    assert project.name == "Ezytix Tech"
    
    # Check by case-insensitive name
    project = redmine.get_project("erp system")
    assert project is not None
    assert project.id == 2
