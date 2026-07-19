from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.db.session import get_db
from api.db.models import User, UserSettings
from api.auth.deps import get_current_user
from api.schemas import UserSettingsUpdate, UserSettingsOut
from api.services.user_settings import apply_settings_update, settings_to_public

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsOut)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not row:
        row = UserSettings(user_id=user.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return settings_to_public(row)


@router.put("", response_model=UserSettingsOut)
def update_settings(
    body: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not row:
        row = UserSettings(user_id=user.id)
        db.add(row)
        db.flush()
    apply_settings_update(row, body)
    db.commit()
    db.refresh(row)
    return settings_to_public(row)
