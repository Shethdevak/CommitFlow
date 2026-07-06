import pytest
from typer.testing import CliRunner
from app.cli import app

runner = CliRunner()

def test_cli_help():
    """Verifies that the CLI help runs successfully and prints commands description."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sync" in result.stdout
    assert "test-connection" in result.stdout
    assert "list-projects" in result.stdout
    assert "show-cache" in result.stdout


def test_cli_sync_validation():
    """Verifies that the sync command fails if no date or today flag is specified."""
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "Please specify either --today or --date YYYY-MM-DD" in result.stdout


def test_cli_sync_invalid_date():
    """Verifies that the sync command raises error on malformed date formats."""
    result = runner.invoke(app, ["sync", "--date", "not-a-date"])
    assert result.exit_code == 1
    assert "Invalid date format. Use YYYY-MM-DD." in result.stdout


def test_cli_test_connection_missing_settings(mocker):
    """Verifies that test-connection catches load settings failure gracefully."""
    # Mock settings load to raise an exception
    mocker.patch("app.cli.load_settings", side_effect=Exception("Env missing"))
    
    result = runner.invoke(app, ["test-connection"])
    assert result.exit_code == 1
    assert "Settings error" in result.stdout
