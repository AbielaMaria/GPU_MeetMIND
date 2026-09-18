"""
MeetMind — real auth: password hashing, sessions, and the
/api/auth/* + /api/users endpoints the frontend mock used to fake.

Session model
-------------
A random token is stored server-side in the `sessions` table (see
database.py) and handed to the browser as an HttpOnly cookie.

  * "Remember me" checked  -> cookie carries Max-Age (persists across
    browser restarts, like before).
  * "Remember me" unchecked -> cookie has NO Max-Age, which makes it a
    browser*-session* cookie: the browser discards it when the tab/
    browser is closed, so the next visit requires signing in again.

Either way the DB row also carries its own expiry, so a leaked/never-
closed cookie can't be used forever.

Role is decided here, from the DB row — never trusted from the client.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import database as db

SESSION_COOKIE = "meetmind_session"
REMEMBER_SECONDS = 30 * 24 * 60 * 60   # 30 days, when "remember me" is checked
UNREMEMBERED_SESSION_HOURS = 12        # absolute cap even within one browser session

router = APIRouter(prefix="/api", tags=["auth"])


# ============================================================
# PASSWORDS
# ============================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ============================================================
# SESSION HELPERS / DEPENDENCIES
# ============================================================

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return db.get_session_user(token)


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def landing_path_for_role(role: str) -> str:
    # Mirrors frontend/assets/auth-store.js's landingPathForRole().
    return "/admin" if role == "admin" else "/app"


def _public_user(user: dict) -> dict:
    return {
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "status": user["status"],
        "createdAt": user["created_at"],
    }


EMAIL_RE_MSG = "Enter a valid email address."


def _norm_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail=EMAIL_RE_MSG)
    return email


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = False


class AdminUserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"
    status: str = "active"


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


# ============================================================
# AUTH ROUTES
# ============================================================

@router.post("/auth/register")
def register(payload: RegisterRequest):
    email = _norm_email(payload.email)
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required.")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    user = db.create_user(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        role="user",
        status="active",
    )
    return _public_user(user)


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response):
    email = _norm_email(payload.email)
    user = db.get_user_by_email(email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="This account is inactive. Contact your administrator.")

    now = datetime.now(timezone.utc)
    if payload.remember:
        expires_at = now + timedelta(seconds=REMEMBER_SECONDS)
        cookie_max_age = REMEMBER_SECONDS
    else:
        expires_at = now + timedelta(hours=UNREMEMBERED_SESSION_HOURS)
        cookie_max_age = None  # session cookie: browser drops it on close

    token = secrets.token_urlsafe(32)
    db.create_session(token=token, user_id=user["id"], expires_at=expires_at.isoformat())

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=cookie_max_age,
        path="/",
    )
    return _public_user(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/session")
def session(user: dict = Depends(require_user)):
    return _public_user(user)


# ============================================================
# ADMIN — USER MANAGEMENT
# ============================================================

@router.get("/users")
def admin_list_users(_: dict = Depends(require_admin)):
    return [_public_user(u) for u in db.list_users()]


@router.post("/users")
def admin_create_user(payload: AdminUserCreate, _: dict = Depends(require_admin)):
    email = _norm_email(payload.email)
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required.")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="A user with that email already exists.")

    user = db.create_user(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        role="admin" if payload.role == "admin" else "user",
        status="inactive" if payload.status == "inactive" else "active",
    )
    return _public_user(user)


@router.patch("/users/{email}")
def admin_update_user(email: str, payload: AdminUserUpdate, _: dict = Depends(require_admin)):
    existing = db.get_user_by_email(_norm_email(email))
    if not existing:
        raise HTTPException(status_code=404, detail="User not found.")

    fields = {}
    if payload.username is not None:
        if not payload.username.strip():
            raise HTTPException(status_code=400, detail="Username is required.")
        fields["username"] = payload.username.strip()
    if payload.email is not None:
        new_email = _norm_email(payload.email)
        clash = db.get_user_by_email(new_email)
        if clash and clash["id"] != existing["id"]:
            raise HTTPException(status_code=400, detail="Another user already uses that email.")
        fields["email"] = new_email
    if payload.password:
        fields["password_hash"] = hash_password(payload.password)
    if payload.role is not None:
        fields["role"] = "admin" if payload.role == "admin" else "user"
    if payload.status is not None:
        fields["status"] = "inactive" if payload.status == "inactive" else "active"

    user = db.update_user(existing["id"], **fields)
    return _public_user(user)


@router.delete("/users/{email}")
def admin_delete_user(email: str, admin_user: dict = Depends(require_admin)):
    target = _norm_email(email)
    if target == admin_user["email"]:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")
    if not db.delete_user(target):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}
