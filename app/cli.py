import os
import sys
from datetime import datetime, date
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from loguru import logger

from app.config.settings import load_settings
from app.database.connection import init_db, db_session
from app.database.repository import DatabaseRepository
from app.github.client import GitHubClient
from app.gitlab.client import GitLabClient
from app.redmine.client import RedmineClient
from app.services.sync import SyncService
from app.services.factory import build_sync_service

app = typer.Typer(help="CommitFlow: AI-powered Worklog Automation CLI for Redmine")
console = Console()

def get_sync_service() -> SyncService:
    """Helper to initialize settings and all required services."""
    try:
        settings = load_settings()
    except Exception as e:
        rprint(f"[bold red]Configuration Error:[/bold red] {e}")
        sys.exit(1)

    try:
        return build_sync_service(settings)
    except Exception as e:
        rprint(f"[bold red]Service init error:[/bold red] {e}")
        sys.exit(1)

@app.callback()
def main():
    """AI Powered Redmine Worklog Automator."""
    # Configure Loguru output to only write to file, keeping CLI clean or setting format
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    logger.remove()
    logger.add(
        os.path.join(log_dir, "app.log"),
        rotation="10 MB",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )

@app.command(name="sync")
def sync_command(
    today: bool = typer.Option(False, "--today", help="Sync commits from today"),
    sync_date_str: Optional[str] = typer.Option(
        None, "--date", help="Sync commits for a specific date (format: YYYY-MM-DD)"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview to-dos and hours without writing anything to Redmine",
    ),
):
    """Synchronizes Git commits for a given date, processes them via AI, and updates Redmine."""
    if not today and not sync_date_str:
        rprint("[bold yellow]Please specify either --today or --date YYYY-MM-DD[/bold yellow]")
        raise typer.Exit(code=1)

    target_date = sync_date_str if sync_date_str else datetime.utcnow().strftime("%Y-%m-%d")
    
    # Validate format of custom date
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        rprint("[bold red]Invalid date format. Use YYYY-MM-DD.[/bold red]")
        raise typer.Exit(code=1)

    mode = "[DRY RUN] " if dry_run else ""
    rprint(f"[bold blue]{mode}Initializing sync for date: {target_date}...[/bold blue]")
    service = get_sync_service()
    
    try:
        result = service.sync_date(target_date, dry_run=dry_run)
        if result.errors:
            rprint("[bold red]Sync completed with errors:[/bold red]")
            for err in result.errors:
                rprint(f" - {err}")

        if dry_run:
            rprint("[bold yellow]DRY RUN — nothing was written to Redmine.[/bold yellow]")
            rprint(f" - Commits found: {result.processed_commits_count}")
            rprint(f" - Cached commits reused: {result.cached_commits_count}")
            rprint(f" - To-dos that WOULD be created: {result.todos_planned}")
            rprint(f" - Hours that WOULD be logged: {result.hours_logged}h (goal: {service.settings.daily_hour_goal}h)")

            if result.planned_todos:
                table = Table(title=f"Preview: to-dos for {target_date}")
                table.add_column("#", style="cyan", no_wrap=True)
                table.add_column("Hours", style="yellow")
                table.add_column("Project", style="magenta")
                table.add_column("Feature", style="green")
                table.add_column("Subject")
                table.add_column("Type", style="dim")
                for i, todo in enumerate(result.planned_todos, start=1):
                    table.add_row(
                        str(i),
                        f"{todo.hours}h",
                        todo.project_name,
                        todo.feature_name,
                        todo.subject[:80],
                        "synthetic" if todo.is_synthetic else "commit",
                    )
                console.print(table)
        else:
            rprint(f"[bold green]Sync successfully completed![/bold green]")
            rprint(f" - Commits Processed: {result.processed_commits_count}")
            rprint(f" - Cached commits reused: {result.cached_commits_count}")
            rprint(f" - To-dos planned: {result.todos_planned}")
            rprint(f" - Redmine Issues Created: {len(result.created_issues)}")
            rprint(f" - Redmine Issues Updated: {len(result.updated_issues)}")
            rprint(f" - Time entries created: {result.time_entries_created}")
            rprint(f" - Hours logged: {result.hours_logged}h (goal: {service.settings.daily_hour_goal}h)")

        if result.unmapped_repos:
            rprint(f"[yellow] - Unmapped repos ({len(result.unmapped_repos)}):[/yellow]")
            for repo in result.unmapped_repos[:10]:
                rprint(f"   • {repo}")
            if len(result.unmapped_repos) > 10:
                rprint(f"   … and {len(result.unmapped_repos) - 10} more")
    except Exception as e:
        rprint(f"[bold red]Sync critical failure: {e}[/bold red]")
        raise typer.Exit(code=1)

@app.command(name="test-connection")
def test_connection():
    """Validates connectivity to configured GitHub, GitLab, and Redmine services."""
    rprint("[bold blue]Testing service connectivity...[/bold blue]")
    
    # Simple manual setup check
    try:
        settings = load_settings()
    except Exception as e:
        rprint(f"[bold red]Settings error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Redmine
    rprint(f"Redmine URL: {settings.redmine_url}")
    redmine = RedmineClient(base_url=settings.redmine_url, api_key=settings.redmine_api_key)
    try:
        projects = redmine.get_projects()
        rprint(f"[green]✔ Redmine connected successfully. Found {len(projects)} projects.[/green]")
    except Exception as e:
        rprint(f"[red]✘ Redmine connection failed: {e}[/red]")

    # GitHub
    if settings.github_token:
        github = GitHubClient(token=settings.github_token)
        try:
            # Try to fetch current rate limit to test credentials
            response = github._request("GET", "rate_limit")
            rprint("[green]✔ GitHub token validated successfully.[/green]")
        except Exception as e:
            rprint(f"[red]✘ GitHub connection failed: {e}[/red]")
    else:
        rprint("[yellow]! GitHub token not configured. Skipping test.[/yellow]")

    # GitLab
    if settings.gitlab_token:
        gitlab = GitLabClient(token=settings.gitlab_token, base_url=settings.gitlab_api_url)
        try:
            # Fetch gitlab version to test connectivity
            response = gitlab._request("GET", "version")
            rprint(f"[green]✔ GitLab API connected successfully (Version: {response.json().get('version')}).[/green]")
        except Exception as e:
            rprint(f"[red]✘ GitLab connection failed: {e}[/red]")
    else:
        rprint("[yellow]! GitLab token not configured. Skipping test.[/yellow]")

@app.command(name="list-projects")
def list_projects():
    """Lists all available projects in the configured Redmine server."""
    service = get_sync_service()
    try:
        projects = service.redmine_client.get_projects()
        table = Table(title="Redmine Projects")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Identifier", style="magenta")

        for p in projects:
            table.add_row(str(p.id), p.name, p.identifier)

        console.print(table)
    except Exception as e:
        rprint(f"[bold red]Failed to load projects: {e}[/bold red]")

@app.command(name="list-features")
def list_features(
    project_identifier: str = typer.Argument(..., help="Redmine Project identifier or Name")
):
    """Lists Features (parent issues) associated with a given Redmine project."""
    service = get_sync_service()
    try:
        project = service.redmine_client.get_project(project_identifier)
        if not project:
            rprint(f"[bold red]Project '{project_identifier}' not found.[/bold red]")
            raise typer.Exit(code=1)

        features = service.redmine_client.get_features(project.id)
        table = Table(title=f"Features in project: {project.name}")
        table.add_column("Issue ID", style="cyan", no_wrap=True)
        table.add_column("Feature Title", style="green")

        for f in features:
            table.add_row(str(f.id), f.subject)

        console.print(table)
    except Exception as e:
        rprint(f"[bold red]Failed to load features: {e}[/bold red]")

@app.command(name="show-cache")
def show_cache():
    """Prints all prediction entries currently cached in the SQLite database."""
    settings = load_settings()
    init_db(settings.db_path)
    
    with db_session() as session:
        db_repo = DatabaseRepository(session)
        entries = db_repo.get_all_cache_entries()

    if not entries:
        rprint("[bold yellow]Cache is empty.[/bold yellow]")
        return

    table = Table(title="AI Prediction Cache")
    table.add_column("Commit Hash", style="cyan")
    table.add_column("Repository", style="magenta")
    table.add_column("Predicted Feature", style="green")
    table.add_column("Confidence", style="yellow")
    table.add_column("Provider", style="blue")
    table.add_column("Created At", style="dim")

    for e in entries:
        table.add_row(
            e.commit_hash[:10],
            e.repository,
            e.predicted_feature,
            f"{e.confidence}%",
            e.provider,
            e.created_at.strftime("%Y-%m-%d %H:%M")
        )

    console.print(table)

@app.command(name="clear-cache")
def clear_cache():
    """Wipes all cached AI classification choices from the SQLite database."""
    settings = load_settings()
    init_db(settings.db_path)
    
    with db_session() as session:
        db_repo = DatabaseRepository(session)
        count = db_repo.clear_cache()
        
    rprint(f"[bold green]Successfully cleared prediction cache ({count} entries deleted).[/bold green]")

@app.command(name="add-feedback")
def add_feedback(
    commit_hash: str = typer.Option(..., "--commit", help="Commit hash that was misclassified"),
    repository: str = typer.Option(..., "--repo", help="Git repository (e.g. owner/repo)"),
    commit_msg: str = typer.Option(..., "--msg", help="Commit message summary"),
    predicted: str = typer.Option(..., "--predicted", help="The feature name originally predicted"),
    corrected: str = typer.Option(..., "--corrected", help="The true corrected feature name in Redmine")
):
    """Registers manual user corrections to the learning system DB to tune future AI prompts."""
    settings = load_settings()
    init_db(settings.db_path)
    
    with db_session() as session:
        db_repo = DatabaseRepository(session)
        db_repo.add_feedback(
            commit_hash=commit_hash,
            repository=repository,
            commit_message=commit_msg,
            predicted_feature=predicted,
            corrected_feature=corrected
        )
        
    rprint(f"[bold green]Correction added successfully. This correction will guide future classifications.[/bold green]")

@app.command(name="export-report")
def export_report(
    date_str: str = typer.Argument(..., help="Target date to export (format: YYYY-MM-DD)")
):
    """Exports activity reports (Markdown, HTML, CSV) for a target date to the reports folder."""
    # Run sync service to prepare data
    service = get_sync_service()
    rprint(f"[bold blue]Exporting reports for {date_str}...[/bold blue]")
    try:
        # Resolves reports directly
        result = service.sync_date(date_str)
        rprint(f"[bold green]Reports generated under reports/ folder for {date_str}![/bold green]")
    except Exception as e:
        rprint(f"[bold red]Failed to export reports: {e}[/bold red]")

if __name__ == "__main__":
    app()
