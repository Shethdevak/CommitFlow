from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from backend.config import get_api_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int,
    email: Optional[str] = None,
    *,
    remember_me: bool = False,
) -> str:
    settings = get_api_settings()
    hours = settings.jwt_remember_hours if remember_me else settings.jwt_expire_hours
    expire = datetime.now(timezone.utc) + timedelta(hours=hours)
    payload = {"sub": str(user_id), "email": email, "exp": expire, "rm": bool(remember_me)}
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def create_password_reset_token(user_id: int, email: str) -> str:
    """Short-lived token issued only after a valid reset OTP."""
    settings = get_api_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "purpose": "password_reset",
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def decode_password_reset_token(token: str) -> dict:
    payload = decode_access_token(token)
    if payload.get("purpose") != "password_reset":
        raise JWTError("Invalid reset token")
    return payload


def decode_access_token(token: str) -> dict:
    settings = get_api_settings()
    return jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
