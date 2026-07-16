from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.db.session import get_db
from api.db.models import User, UserSettings
from api.auth.deps import get_current_user
from api.config import get_api_settings
from api.schemas import SyncRequest, SyncResultOut, PlannedTodoOut, CommitPlannedRequest
from api.services.user_settings import build_settings_mapping, ensure_user_paths
from app.config.settings import Settings
from app.models.domain import WorkTodo, SyncResult
from app.services.factory import build_sync_service

router = APIRouter(prefix="/sync", tags=["sync"])


def _service_for_user(user: User, db: Session):
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=400, detail="Save your settings first")

    api_settings = get_api_settings()
    try:
        db_path, mappings_path = ensure_user_paths(
            user.id, api_settings.api_user_data_dir, row.mappings_yaml
        )
        mapping = build_settings_mapping(row, db_path=db_path, mappings_path=mappings_path)
        settings = Settings.from_mapping(mapping)
        service = build_sync_service(settings)
        return service, settings
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _todo_out(t) -> PlannedTodoOut:
    return PlannedTodoOut(
        subject=t.subject,
        hours=t.hours,
        project_name=t.project_name,
        feature_name=t.feature_name,
        is_synthetic=t.is_synthetic,
        project_id=t.project_id,
        parent_issue_id=t.parent_issue_id,
        description=t.description or "",
    )


def _result_out(result: SyncResult) -> SyncResultOut:
    return SyncResultOut(
        date=result.date,
        dry_run=result.dry_run,
        processed_commits_count=result.processed_commits_count,
        cached_commits_count=result.cached_commits_count,
        todos_planned=result.todos_planned,
        hours_logged=result.hours_logged,
        created_issues=result.created_issues,
        updated_issues=result.updated_issues,
        time_entries_created=result.time_entries_created,
        errors=result.errors,
        unmapped_repos=result.unmapped_repos,
        planned_todos=[_todo_out(t) for t in result.planned_todos],
    )


@router.post("", response_model=SyncResultOut)
def run_sync(
    body: SyncRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the same SyncService as the CLI (dry-run or full) using this user's settings."""
    service, settings = _service_for_user(user, db)

    if body.date:
        target = body.date
    else:
        try:
            tz = ZoneInfo(settings.timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        target = datetime.now(tz).strftime("%Y-%m-%d")

    try:
        result = service.sync_date(target, dry_run=body.dry_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

    return _result_out(result)


@router.post("/commit", response_model=SyncResultOut)
def commit_planned(
    body: CommitPlannedRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Commit a dry-run plan to Redmine without re-running fetch/AI."""
    if not body.planned_todos:
        raise HTTPException(status_code=400, detail="No planned to-dos to commit")

    service, _settings = _service_for_user(user, db)

    todos = [
        WorkTodo(
            subject=t.subject,
            description=t.description or t.subject,
            hours=t.hours,
            project_id=t.project_id,
            project_name=t.project_name,
            feature_name=t.feature_name,
            parent_issue_id=t.parent_issue_id,
            is_synthetic=t.is_synthetic,
        )
        for t in body.planned_todos
    ]
    # Guard: need valid project ids from dry-run payload
    if any(t.project_id <= 0 for t in todos):
        raise HTTPException(
            status_code=400,
            detail="This preview is missing project IDs. Run dry-run again, then click Commit all.",
        )

    try:
        result = service.apply_planned_todos(body.date, todos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commit failed: {e}")

    return _result_out(result)
