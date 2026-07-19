import secrets
from urllib.parse import urlencode
import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from api.db.session import get_db
from api.db.models import User, UserSettings
from api.schemas import RegisterRequest, LoginRequest, AuthResponse, UserOut
from api.auth.tokens import hash_password, verify_password, create_access_token
from api.auth.deps import get_current_user
from api.auth.cookies import set_auth_cookie, clear_auth_cookie
from api.config import get_api_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/github/login")
def github_login():
    settings = get_api_settings()
    if not settings.github_oauth_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth is not configured on the server")

    redirect_uri = f"{_api_public_base()}/api/auth/github/callback"
    params = urlencode({
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": secrets.token_urlsafe(16),
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
def github_callback(code: str, db: Session = Depends(get_db)):
    settings = get_api_settings()
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(status_code=501, detail="GitHub OAuth is not configured")

    redirect_uri = f"{_api_public_base()}/api/auth/github/callback"
    token_res = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=20,
    )
    token_res.raise_for_status()
    access = token_res.json().get("access_token")
    if not access:
        raise HTTPException(status_code=400, detail="GitHub OAuth failed")

    headers = {
        "Authorization": f"Bearer {access}",
        "Accept": "application/vnd.github+json",
    }
    profile = requests.get("https://api.github.com/user", headers=headers, timeout=20).json()
    emails_resp = requests.get("https://api.github.com/user/emails", headers=headers, timeout=20)
    emails = emails_resp.json() if emails_resp.ok else []

    primary_email = None
    if isinstance(emails, list):
        for e in emails:
            if e.get("primary") and e.get("verified"):
                primary_email = e.get("email")
                break
        if not primary_email and emails:
            primary_email = emails[0].get("email")

    github_id = str(profile.get("id"))
    login_name = profile.get("login")
    user = db.query(User).filter(User.github_id == github_id).first()
    if not user and primary_email:
        user = db.query(User).filter(User.email == primary_email.lower()).first()
        if user:
            user.github_id = github_id
            user.github_login = login_name

    if not user:
        user = User(
            email=primary_email.lower() if primary_email else None,
            display_name=profile.get("name") or login_name,
            github_id=github_id,
            github_login=login_name,
        )
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id))

    db.commit()
    db.refresh(user)
    jwt_token = create_access_token(user.id, user.email, remember_me=True)
    dest = f"{settings.api_frontend_url.rstrip('/')}/auth/callback"
    resp = RedirectResponse(dest)
    set_auth_cookie(resp, jwt_token, remember_me=True)
    return resp


def _api_public_base() -> str:
    return get_api_settings().api_public_url.rstrip("/")
