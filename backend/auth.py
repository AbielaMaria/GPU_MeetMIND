"""
MeetMind — real auth: password hashing, sessions, and the
/api/auth/* + /api/users endpoints the frontend mock used to fake.

Session model
-------------
A random token is stored server-side in the `sessions` table (see
database.py) and handed to the browser as an HttpOnly cookie with a
30-day Max-Age, so signing in persists across browser restarts. The
DB row also carries its own expiry, so a leaked/never-closed cookie
can't be used forever.

Role is decided here, from the DB row — never trusted from the client.

Login accepts either a username or an email in the same field; see
`_find_user_by_identifier`.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import database as db

SESSION_COOKIE = "meetmind_session"
SESSION_SECONDS = 30 * 24 * 60 * 60   # 30 days

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


def _find_user_by_identifier(identifier: str) -> Optional[dict]:
    """Login identifier is a username or an email — tell them apart by '@'."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        return db.get_user_by_email(identifier.lower())
    return db.get_user_by_username(identifier)


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    identifier: str  # username or email
    password: str


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
    user = _find_user_by_identifier(payload.identifier)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="This account is inactive. Contact your administrator.")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)
    token = secrets.token_urlsafe(32)
    db.create_session(token=token, user_id=user["id"], expires_at=expires_at.isoformat())

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_SECONDS,
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