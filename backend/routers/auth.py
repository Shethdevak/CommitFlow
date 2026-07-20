import secrets
from urllib.parse import urlencode
import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import User, UserSettings
from backend.schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserOut,
    user_to_out,
    RegisterPendingResponse,
    OtpSendRequest,
    OtpVerifyRequest,
    ForgotPasswordRequest,
    VerifyResetCodeRequest,
    VerifyResetCodeResponse,
    ResetPasswordRequest,
    OtpMetaResponse,
    UpdateDisplayNameRequest,
    ChangePasswordRequest,
    ChangeEmailRequest,
    VerifyChangeEmailRequest,
)
from backend.auth.tokens import (
    hash_password,
    verify_password,
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    decode_access_token,
)
from backend.auth.deps import get_current_user
from backend.auth.cookies import COOKIE_NAME, set_auth_cookie, clear_auth_cookie
from backend.config import get_api_settings
from backend.services.otp import create_and_send_otp, verify_otp
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["auth"])


def _remember_from_request(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        return bool(decode_access_token(token).get("rm"))
    except JWTError:
        return False


def _refresh_session_cookie(request: Request, response: Response, user: User) -> None:
    remember = _remember_from_request(request)
    token = create_access_token(user.id, user.email, remember_me=remember)
    set_auth_cookie(response, token, remember_me=remember)


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
    return AuthResponse(user=user_to_out(user))


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
    return AuthResponse(user=user_to_out(user))


@router.post("/password/forgot", response_model=OtpMetaResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email_l = body.email.lower()
    user = db.query(User).filter(User.email == email_l).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=404, detail="No account found for that email.")
    meta = create_and_send_otp(db, email=email_l, purpose="reset")
    return OtpMetaResponse(**meta)


@router.post("/password/verify-code", response_model=VerifyResetCodeResponse)
def verify_reset_code(body: VerifyResetCodeRequest, db: Session = Depends(get_db)):
    email_l = body.email.lower()
    user = db.query(User).filter(User.email == email_l).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=404, detail="No account found for that email.")

    verify_otp(db, email=email_l, purpose="reset", code=body.code)
    reset_token = create_password_reset_token(user.id, email_l)
    return VerifyResetCodeResponse(email=email_l, reset_token=reset_token)


@router.post("/password/reset")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_password_reset_token(body.reset_token)
    except JWTError:
        raise HTTPException(
            status_code=400,
            detail="Reset session expired. Request a new code.",
        ) from None

    user_id = int(payload["sub"])
    email_l = (payload.get("email") or "").lower()
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=404, detail="Account not found.")
    if user.email and user.email.lower() != email_l:
        raise HTTPException(status_code=400, detail="Reset session invalid.")

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
    return user_to_out(user)


@router.patch("/account/display-name", response_model=UserOut)
def update_display_name(
    body: UpdateDisplayNameRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.display_name = body.display_name
    db.commit()
    db.refresh(user)
    return user_to_out(user)


@router.post("/account/password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="This account has no password. Set one via forgot password, or sign in with GitHub only.",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current one.")

    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True, "message": "Password updated."}


@router.post("/account/email/request", response_model=OtpMetaResponse)
def request_email_change(
    body: ChangeEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Password confirmation is required to change email. Set a password first.",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_email = body.new_email.lower().strip()
    if user.email and user.email.lower() == new_email:
        raise HTTPException(status_code=400, detail="That is already your current email.")

    taken = db.query(User).filter(User.email == new_email, User.id != user.id).first()
    if taken:
        raise HTTPException(status_code=400, detail="That email is already in use.")

    meta = create_and_send_otp(
        db,
        email=new_email,
        purpose="email_change",
        user_id=user.id,
    )
    return OtpMetaResponse(**meta)


@router.post("/account/email/verify", response_model=UserOut)
def verify_email_change(
    body: VerifyChangeEmailRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_email = body.new_email.lower().strip()
    if user.email and user.email.lower() == new_email:
        raise HTTPException(status_code=400, detail="That is already your current email.")

    taken = db.query(User).filter(User.email == new_email, User.id != user.id).first()
    if taken:
        raise HTTPException(status_code=400, detail="That email is already in use.")

    verify_otp(
        db,
        email=new_email,
        purpose="email_change",
        code=body.code,
        user_id=user.id,
    )

    user.email = new_email
    user.email_verified = True
    db.commit()
    db.refresh(user)
    _refresh_session_cookie(request, response, user)
    return user_to_out(user)


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
