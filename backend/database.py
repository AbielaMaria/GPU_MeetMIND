"""
MeetMind — SQLite persistence layer.

Owns the on-disk database (backend/meetmind.db): user accounts and
login sessions. This module only talks to SQLite — password hashing
and cookie/session-cookie policy live in auth.py, which calls into
these functions.

Every user-registered-from-any-machine / login-from-any-machine
scenario works because this file (not the browser) is now the single
source of truth for accounts, shared by every client that talks to
this backend instance.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meetmind.db"


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
        """)
        _migrate_users_otp_columns(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        # One row per processed meeting: the transcript it produced and the
        # summary generated from it (stored as JSON, exactly as the
        # /api/meeting/summarize response shape, so the frontend can render
        # a saved meeting with the same code it renders a fresh one).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                summary_json TEXT,
                mindmap_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_meetings_user "
            "ON meetings(user_id, created_at DESC)"
        )
        _migrate_meetings_mindmap_column(conn)


def _migrate_users_otp_columns(conn):
    """
    Adds OTP email-verification columns to a `users` table created before
    they existed. SQLite has no `ADD COLUMN IF NOT EXISTS`, so we check
    PRAGMA table_info first. Pre-existing rows are grandfathered in as
    already verified — otherwise every account created before this
    migration (including the seed admin) would be locked out on next login.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "email_verified" in existing:
        return

    conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE users ADD COLUMN otp_code_hash TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN otp_expires_at TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN otp_attempts INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE users SET email_verified = 1")


def _migrate_meetings_mindmap_column(conn):
    """Adds mindmap_json to a `meetings` table created before it existed."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(meetings)")}
    if "mindmap_json" in existing:
        return

    conn.execute("ALTER TABLE meetings ADD COLUMN mindmap_json TEXT")


# ============================================================
# USERS
# ============================================================

def list_users():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_user_by_email(email):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_username(username):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_user(username, email, password_hash, role="user", status="active"):
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, role, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, password_hash, role, status, created_at),
        )
        user_id = cur.lastrowid
    return get_user_by_id(user_id)


def update_user(user_id, **fields):
    if not fields:
        return get_user_by_id(user_id)
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [user_id]
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {columns} WHERE id = ?", values)
    return get_user_by_id(user_id)


def delete_user(email):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE email = ?", (email,))
        return cur.rowcount > 0


def ensure_seed_admin(password_hash):
    """Bootstrap a single admin account on a brand-new database only."""
    if list_users():
        return
    create_user(
        username="admin",
        email="admin@gmail.com",
        password_hash=password_hash,
        role="admin",
        status="active",
    )


# ============================================================
# SESSIONS
# ============================================================

def create_session(token, user_id, expires_at):
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, created_at, expires_at),
        )


def get_session_user(token):
    with _connect() as conn:
        row = conn.execute(
            "SELECT sessions.expires_at AS session_expires_at, users.* "
            "FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None

        data = dict(row)
        expires_at = datetime.fromisoformat(data.pop("session_expires_at"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        return data


def delete_session(token):
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ============================================================
# MEETINGS
# ============================================================

def create_meeting(user_id, title, transcript, summary_json, mindmap_json=None):
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (user_id, title, transcript, summary_json, mindmap_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, transcript, summary_json, mindmap_json, created_at),
        )
        meeting_id = cur.lastrowid
    return get_meeting(meeting_id)


def find_recent_meeting_by_transcript(user_id, transcript, within_hours=6):
    """
    The id of this user's most recent meeting holding exactly this
    transcript, or None.

    Both /api/meeting/summarize and /api/meeting/mindmap open the meeting
    row lazily, so when they run against the same recording at the same
    time neither one knows about the row the other has just inserted.
    Looking the recording up by its own transcript lets the second one
    join that row instead of logging the same meeting twice. The time
    window keeps an unrelated old meeting that happens to share a very
    short transcript out of it.
    """
    if not transcript:
        return None

    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=within_hours)
    ).isoformat()

    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM meetings "
            "WHERE user_id = ? AND transcript = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, transcript, cutoff),
        ).fetchone()
        return row["id"] if row else None


def get_meeting(meeting_id):
    """Full record, including the owner's id so callers can check access."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT meetings.*, users.username AS username, users.email AS email "
            "FROM meetings JOIN users ON users.id = meetings.user_id "
            "WHERE meetings.id = ?",
            (meeting_id,),
        ).fetchone()
        return dict(row) if row else None


def update_meeting(meeting_id, **fields):
    """Patch title/summary_json (or any column) on an existing meeting."""
    if not fields:
        return get_meeting(meeting_id)
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [meeting_id]
    with _connect() as conn:
        conn.execute(f"UPDATE meetings SET {columns} WHERE id = ?", values)
    return get_meeting(meeting_id)


def list_meetings(user_id=None):
    """
    Newest first. Without `user_id` this returns every user's meetings
    (admin view) with the owner attached. The transcript/summary bodies are
    left out — listings only need the headline fields.
    """
    query = (
        "SELECT meetings.id, meetings.title, meetings.created_at, meetings.user_id, "
        "meetings.summary_json IS NOT NULL AS has_summary, "
        "meetings.mindmap_json IS NOT NULL AS has_mindmap, "
        "LENGTH(meetings.transcript) AS transcript_chars, "
        "users.username AS username, users.email AS email "
        "FROM meetings JOIN users ON users.id = meetings.user_id "
    )
    params = ()
    if user_id is not None:
        query += "WHERE meetings.user_id = ? "
        params = (user_id,)
    query += "ORDER BY meetings.created_at DESC"

    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]