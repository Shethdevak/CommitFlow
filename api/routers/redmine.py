"""Read-only Redmine day log for the signed-in user."""

from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import requests
from api.db.session import get_db
from api.db.models import User, UserSettings
from api.auth.deps import get_current_user
from api.config import get_api_settings
from api.schemas import RedmineDayOut, RedmineDayEntryOut
from api.services.user_settings import build_settings_mapping, ensure_user_paths
from app.config.settings import Settings
from app.redmine.client import RedmineClient

router = APIRouter(prefix="/redmine", tags=["redmine"])


def _settings_for_user(user: User, db: Session) -> Settings:
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=400, detail="Save your settings first")

    api_settings = get_api_settings()
    try:
        db_path, mappings_path = ensure_user_paths(
            user.id, api_settings.api_user_data_dir, row.mappings_yaml
        )
        mapping = build_settings_mapping(row, db_path=db_path, mappings_path=mappings_path)
        return Settings.from_mapping(mapping)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/day", response_model=RedmineDayOut)
def day_log(
    date: str | None = Query(None, description="YYYY-MM-DD; default today in user timezone"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List this user's Redmine time entries for a spent_on date."""
    settings = _settings_for_user(user, db)

    if date:
        target = date.strip()
    else:
        try:
            tz = ZoneInfo(settings.timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        target = datetime.now(tz).strftime("%Y-%m-%d")

    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from e

    client = RedmineClient(base_url=settings.redmine_url, api_key=settings.redmine_api_key)
    try:
        raw = client.list_time_entries_for_date(target)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        if status == 401:
            raise HTTPException(
                status_code=401,
                detail="Redmine rejected your API key (401). Check REDMINE_API_KEY in Integrations.",
            ) from e
        raise HTTPException(status_code=502, detail=f"Redmine error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to load Redmine day log: {e}") from e

    base = settings.redmine_url.rstrip("/")
    entries = [
        RedmineDayEntryOut(
            id=item.get("id"),
            hours=float(item.get("hours") or 0),
            spent_on=item.get("spent_on") or target,
            comments=item.get("comments") or "",
            issue_id=item.get("issue_id"),
            issue_subject=item.get("issue_subject") or "",
            project_name=item.get("project_name") or "",
            issue_url=f"{base}/issues/{item['issue_id']}" if item.get("issue_id") else None,
        )
        for item in raw
    ]
    total = round(sum(e.hours for e in entries), 2)
    return RedmineDayOut(
        date=target,
        total_hours=total,
        entry_count=len(entries),
        redmine_url=base,
        entries=entries,
    )
