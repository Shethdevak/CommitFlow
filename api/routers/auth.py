import secrets
from urllib.parse import urlencode
import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from api.db.session import get_db
from api.db.models import User, UserSettings
from api.schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserOut,
    RegisterPendingResponse,
    OtpSendRequest,
    OtpVerifyRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    OtpMetaResponse,
)
from api.auth.tokens import hash_password, verify_password, create_access_token
from api.auth.deps import get_current_user
from api.auth.cookies import set_auth_cookie, clear_auth_cookie
from api.config import get_api_settings
from api.services.otp import create_and_send_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterPendingResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
        email_verified=False,
    )
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    db.commit()

    meta = create_and_send_otp(db, email=user.email, purpose="signup")
    return RegisterPendingResponse(
        requires_verification=True,
        email=meta["email"],
        expires_in_seconds=meta["expires_in_seconds"],
        resend_after_seconds=meta["resend_after_seconds"],
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_not_verified",
                "message": "Please verify your email before signing in.",
                "email": user.email,
            },
        )
    token = create_access_token(user.id, user.email, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/otp/send", response_model=OtpMetaResponse)
def send_otp(body: OtpSendRequest, db: Session = Depends(get_db)):
    email_l = body.email.lower()
    if body.purpose == "signup":
        user = db.query(User).filter(User.email == email_l).first()
        if not user:
            raise HTTPException(status_code=404, detail="No account found for that email.")
        if user.email_verified:
            raise HTTPException(status_code=400, detail="Email is already verified. You can sign in.")
    meta = create_and_send_otp(db, email=email_l, purpose=body.purpose)  # type: ignore[arg-type]
    return OtpMetaResponse(**meta)


@router.post("/otp/verify", response_model=AuthResponse)
def verify_signup_otp(body: OtpVerifyRequest, response: Response, db: Session = Depends(get_db)):
    if body.purpose != "signup":
        raise HTTPException(status_code=400, detail="Use /auth/password/reset for password reset.")

    email_l = body.email.lower()
    verify_otp(db, email=email_l, purpose="signup", code=body.code)

    user = db.query(User).filter(User.email == email_l).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    user.email_verified = True
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/password/forgot", response_model=OtpMetaResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always succeeds publicly; only sends mail when the account exists."""
    email_l = body.email.lower()
    user = db.query(User).filter(User.email == email_l).first()
    settings = get_api_settings()
    if not user or not user.password_hash:
        # Avoid account enumeration — return the same shape without sending mail
        return OtpMetaResponse(
            email=email_l,
            purpose="reset",
            expires_in_seconds=int(settings.otp_expire_minutes) * 60,
            resend_after_seconds=int(settings.otp_resend_cooldown_seconds),
        )
    meta = create_and_send_otp(db, email=email_l, purpose="reset")
    return OtpMetaResponse(**meta)


@router.post("/password/reset")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    email_l = body.email.lower()
    verify_otp(db, email=email_l, purpose="reset", code=body.code)

    user = db.query(User).filter(User.email == email_l).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=404, detail="Account not found.")

    user.password_hash = hash_password(body.password)
    user.email_verified = True
    db.commit()
    return {"ok": True, "message": "Password updated. You can sign in."}


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
            email_verified=True,
        )
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id))
    else:
        user.email_verified = True

    db.commit()
    db.refresh(user)
    jwt_token = create_access_token(user.id, user.email, remember_me=True)
    dest = f"{settings.api_frontend_url.rstrip('/')}/auth/callback"
    resp = RedirectResponse(dest)
    set_auth_cookie(resp, jwt_token, remember_me=True)
    return resp


def _api_public_base() -> str:
    return get_api_settings().api_public_url.rstrip("/")
