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

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import database as db
import mailer

logger = logging.getLogger("meetmind")

SESSION_COOKIE = "meetmind_session"
# Marks a browser as waiting on admin approval, so the "pending" page can
# notice the approval (even after a refresh) without holding a password.
# Never a login session — see _pending_token().
PENDING_COOKIE = "meetmind_pending"
PENDING_SECONDS = 7 * 24 * 60 * 60   # 7 days
SESSION_SECONDS = 30 * 24 * 60 * 60   # 30 days

OTP_TTL_SECONDS = 10 * 60   # 10 minutes
OTP_MAX_ATTEMPTS = 5

# Sign-in refusals for unverified accounts. The frontend (auth-forms.js)
# matches these exact strings to pick which page to show, so keep in sync.
UNVERIFIED_LOGIN_MSG = "Please verify your email before signing in."
AWAITING_ADMIN_MSG = "Your account is awaiting verification by an administrator."
ADMIN_UNVERIFIED_MSG = "Your account is unverified. Contact your administrator."
# Not an error: the one-time "your account was approved" notice, sent as a
# refusal on the first sign-in after approval (see login()).
ACCOUNT_APPROVED_MSG = "Your account has been verified by the administrator."

# Only verified accounts can sign in. This switch decides how a
# self-registered account gets verified (see .env / .env.example):
#   true  -> the user enters an emailed OTP (needs working SMTP).
#   false -> no email is sent; the account waits for an admin to verify it.
# Admin-created accounts are verified immediately either way. Once an
# account has been verified (or an admin has unverified it), only an admin
# can change its verification — see `otp_locked` in database.py.
# (Relies on mailer's load_dotenv() above having already loaded .env.)
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "true").strip().lower() not in ("0", "false", "no")

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
    user = db.get_session_user(token)
    # Checked on every request, not just at login, so an admin unverifying
    # someone locks them out immediately rather than when their cookie expires.
    if not user or not user["email_verified"]:
        return None
    return user


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
        "createdAt": user["created_at"],
        "emailVerified": bool(user["email_verified"]),
    }


def _start_session(response: Response, user: dict) -> dict:
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


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# What a pending cookie was issued for:
#   "p" — signed up / was refused sign-in while awaiting approval. Can only
#         answer "has this been approved yet?"; the user signs in normally.
#   "n" — signed in with the right password right after approval (the
#         one-time notice). Also allows the notice's "Continue" button to
#         start the session, so they needn't retype the credentials.
PENDING_WAITING = "p"
PENDING_NOTICE = "n"


def _pending_token(user: dict, expires_at: int, kind: str) -> str:
    """
    Stateless proof that this browser gave `user`'s right password, valid
    until `expires_at` (unix seconds). Keyed on the password hash, so it
    can't be forged without DB access and stops working if the password
    changes. It is never accepted as the login cookie.
    """
    sig = hmac.new(
        user["password_hash"].encode("utf-8"),
        f"pending:{user['id']}:{expires_at}:{kind}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{user['id']}.{expires_at}.{kind}.{sig}"


def _user_from_pending_cookie(request: Request):
    """Returns (user, kind) for a valid, unexpired pending cookie, else None."""
    raw = request.cookies.get(PENDING_COOKIE) or ""
    parts = raw.split(".")
    if len(parts) != 4 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    if parts[2] not in (PENDING_WAITING, PENDING_NOTICE):
        return None
    if int(parts[1]) < datetime.now(timezone.utc).timestamp():
        return None
    user = db.get_user_by_id(int(parts[0]))
    if not user or not hmac.compare_digest(raw, _pending_token(user, int(parts[1]), parts[2])):
        return None
    return user, parts[2]


def _set_pending_cookie(response, user: dict, kind: str = PENDING_WAITING) -> None:
    expires_at = int(datetime.now(timezone.utc).timestamp()) + PENDING_SECONDS
    response.set_cookie(
        key=PENDING_COOKIE,
        value=_pending_token(user, expires_at, kind),
        max_age=PENDING_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _issue_otp(user: dict) -> None:
    """
    Generates a fresh OTP, stores its hash, and emails it. Raises a 502 if
    the send fails — callers that just created `user` are expected to roll
    that creation back so we never leave an unreachable pending account.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
    db.update_user(
        user["id"],
        otp_code_hash=_hash_otp(code),
        otp_expires_at=expires_at.isoformat(),
        otp_attempts=0,
    )
    try:
        mailer.send_otp_email(user["email"], user["username"], code)
    except Exception:
        logger.exception("Could not send OTP email to %s", user["email"])
        raise HTTPException(
            status_code=502,
            detail="Could not send the verification email. Please try again.",
        )


def _unverified_message(user: dict) -> str:
    if user["otp_locked"]:
        return ADMIN_UNVERIFIED_MSG
    if REQUIRE_EMAIL_VERIFICATION:
        return UNVERIFIED_LOGIN_MSG
    return AWAITING_ADMIN_MSG


def _ensure_self_service_otp_allowed(user: dict) -> None:
    """
    The OTP endpoints only serve a first-time verification with the email
    gate on. Anything else is the admin's call — otherwise a user could
    undo an admin's "unverify" by emailing themselves a new code.
    """
    if user["email_verified"]:
        raise HTTPException(status_code=400, detail="This account is already verified.")
    if user["otp_locked"] or not REQUIRE_EMAIL_VERIFICATION:
        raise HTTPException(status_code=403, detail=_unverified_message(user))


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


class VerifyOtpRequest(BaseModel):
    email: str
    code: str


class ResendOtpRequest(BaseModel):
    email: str


class AdminUserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    emailVerified: Optional[bool] = None


# ============================================================
# AUTH ROUTES
# ============================================================

@router.post("/auth/register")
def register(payload: RegisterRequest, response: Response):
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
    )

    if not REQUIRE_EMAIL_VERIFICATION:
        _set_pending_cookie(response, user)
        return {"pendingVerification": True, "awaitingAdmin": True, "email": email}

    try:
        _issue_otp(user)
    except HTTPException:
        db.delete_user(email)
        raise
    return {"pendingVerification": True, "awaitingAdmin": False, "email": email}


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response):
    user = _find_user_by_identifier(payload.identifier)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
    if not user["email_verified"]:
        detail = _unverified_message(user)
        if detail == AWAITING_ADMIN_MSG:
            # Remember this browser is waiting, so the pending page can pick
            # up the approval later (see pending_status).
            refusal = JSONResponse(status_code=403, content={"detail": detail})
            _set_pending_cookie(refusal, user)
            return refusal
        raise HTTPException(status_code=403, detail=detail)

    # One-time "an admin approved your account" notice (see admin_update_user):
    # the first sign-in after approval is answered with the notice instead of
    # a session. The page's "Continue" button then signs them in via
    # continue_after_approval, with no need to type the credentials again.
    if user["approval_notice_pending"]:
        db.update_user(user["id"], approval_notice_pending=0)
        notice = JSONResponse(status_code=403, content={"detail": ACCOUNT_APPROVED_MSG})
        _set_pending_cookie(notice, user, PENDING_NOTICE)   # a refresh keeps the message + Continue
        return notice

    response.delete_cookie(PENDING_COOKIE, path="/")   # signed in: nothing pending any more
    return _start_session(response, user)


@router.get("/auth/pending-status")
def pending_status(request: Request):
    """
    Polled by the "pending approval" page (and run on every load of it) so a
    tab left open — or refreshed — switches to the approved message once an
    admin verifies the account. Seeing it here counts as the one-time notice,
    but it keeps answering "approved" until the user signs in.

    `canContinue` is true only for the first-sign-in-after-approval notice
    (shown with a Continue button); otherwise the user is shown "Back to sign
    in" and signs in normally. Answers "none" without a valid pending cookie.
    """
    found = _user_from_pending_cookie(request)
    if not found:
        return {"state": "none"}
    user, kind = found
    if not user["email_verified"]:
        return {"state": "pending"}
    if user["approval_notice_pending"]:
        db.update_user(user["id"], approval_notice_pending=0)
    # The cookie stays until the user signs in / continues (both drop it), so
    # refreshing the page keeps showing "approved" instead of reverting.
    return {"state": "approved", "canContinue": kind == PENDING_NOTICE}


@router.post("/auth/continue")
def continue_after_approval(request: Request, response: Response):
    """
    The "Continue" button on the first-sign-in approval notice. That notice
    only follows a correct username/password, so once the account is verified
    the session can start without asking for them again.
    """
    found = _user_from_pending_cookie(request)
    if not found or found[1] != PENDING_NOTICE or not found[0]["email_verified"]:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    response.delete_cookie(PENDING_COOKIE, path="/")
    return _start_session(response, found[0])


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


@router.post("/auth/verify-otp")
def verify_otp(payload: VerifyOtpRequest, response: Response):
    email = _norm_email(payload.email)
    user = db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found for that email.")
    _ensure_self_service_otp_allowed(user)

    if not user["otp_code_hash"] or not user["otp_expires_at"]:
        raise HTTPException(status_code=400, detail="No code is pending. Request a new one.")
    if user["otp_attempts"] >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")

    expires_at = datetime.fromisoformat(user["otp_expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="That code has expired. Request a new one.")

    code = (payload.code or "").strip()
    if _hash_otp(code) != user["otp_code_hash"]:
        db.update_user(user["id"], otp_attempts=user["otp_attempts"] + 1)
        raise HTTPException(status_code=400, detail="Incorrect code.")

    user = db.update_user(
        user["id"],
        email_verified=1,
        otp_locked=1,
        otp_code_hash=None,
        otp_expires_at=None,
        otp_attempts=0,
    )
    return {"verified": True, "session": _start_session(response, user)}


@router.post("/auth/resend-otp")
def resend_otp(payload: ResendOtpRequest):
    email = _norm_email(payload.email)
    user = db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found for that email.")
    _ensure_self_service_otp_allowed(user)

    _issue_otp(user)
    return {"ok": True}


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

    # The admin vouches for the account, so it's verified with no OTP.
    user = db.create_user(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        role="admin" if payload.role == "admin" else "user",
        email_verified=1,
        otp_locked=1,
    )
    return _public_user(user)


@router.patch("/users/{email}")
def admin_update_user(email: str, payload: AdminUserUpdate, admin_user: dict = Depends(require_admin)):
    existing = db.get_user_by_email(_norm_email(email))
    if not existing:
        raise HTTPException(status_code=404, detail="User not found.")

    # Same idea as the self-delete guard: an admin can't lock themselves
    # out, which also means there's always at least one working admin.
    is_self = existing["id"] == admin_user["id"]
    if is_self and payload.role is not None and payload.role != "admin":
        raise HTTPException(status_code=400, detail="You can't remove your own admin role.")
    if is_self and payload.emailVerified is False:
        raise HTTPException(status_code=400, detail="You can't unverify your own account.")

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
    # Matches admin_create_user: an account an admin makes an admin is
    # verified, so a promoted user never lands on the unverified page.
    promoted = fields.get("role") == "admin" and existing["role"] != "admin"
    if promoted and payload.emailVerified is None:
        fields.update(
            email_verified=1,
            otp_locked=1,
            otp_code_hash=None,
            otp_expires_at=None,
            otp_attempts=0,
        )
    if payload.emailVerified is not None:
        # Either way verification is now the admin's call: lock out the
        # self-service OTP path and drop any code still pending.
        fields.update(
            email_verified=1 if payload.emailVerified else 0,
            otp_locked=1,
            otp_code_hash=None,
            otp_expires_at=None,
            otp_attempts=0,
        )
        # Flag the one-time approval notice only on a real unverified ->
        # verified flip; unverifying clears it. Re-saving an already
        # verified account leaves a not-yet-shown notice alone.
        if not payload.emailVerified:
            fields["approval_notice_pending"] = 0
        elif not existing["email_verified"]:
            fields["approval_notice_pending"] = 1

    user = db.update_user(existing["id"], **fields)
    if payload.emailVerified is False:
        db.delete_sessions_for_user(existing["id"])
    # DISABLED for now (SMTP isn't available when REQUIRE_EMAIL_VERIFICATION
    # is false). To re-enable: uncomment this block and the helper below,
    # and add `background_tasks: BackgroundTasks` to this route's signature.
    # Tells the user they've been approved — only on the unverified ->
    # verified flip, not when an admin re-saves an already-verified account.
    # if payload.emailVerified and not existing["email_verified"]:
    #     background_tasks.add_task(_send_approved_email, user["email"])
    return _public_user(user)


# def _send_approved_email(to_email: str) -> None:
#     # Runs after the response; a failed send must not undo the approval.
#     try:
#         mailer.send_account_approved_email(to_email)
#     except Exception:
#         logger.exception("Could not send account-approved email to %s", to_email)


@router.delete("/users/{email}")
def admin_delete_user(email: str, admin_user: dict = Depends(require_admin)):
    target = _norm_email(email)
    if target == admin_user["email"]:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")
    if not db.delete_user(target):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}