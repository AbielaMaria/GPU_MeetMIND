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

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meetmind.db"

# The text fields of a doctor prescription, in form order. Mirrors
# meeting_intelligence.DOCTOR_PRESCRIPTION_FIELDS (minus `medicines`, which
# is a list and stored as JSON) — keep the two in step.
PRESCRIPTION_TEXT_FIELDS = (
    "patient_name",
    "age_sex",
    "visit_date",
    "doctor_name",
    "chief_complaint",
    "symptoms_history",
    "allergies",
    "temperature",
    "blood_pressure",
    "pulse_rate",
    "spo2",
    "examination_findings",
    "diagnosis",
    "tests_advised",
    "advice",
    "warning_signs",
    "next_visit",
)

DOCTOR_PROFILE_TEXT_FIELDS = (
    "doctor_name",
    "qualifications",
    "specialization",
    "clinic_name",
    "address",
    "phone",
    "email",
    "timings",
)

# Audio tables and the column naming their parent row. interview_audio is
# created by interview_database.py, which owns the Interview template tables.
_AUDIO_TABLES = {
    "meeting_audio": "meeting_id",
    "doctor_audio": "consultation_id",
    "interview_audio": "interview_id",
}


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
        # WAL lets readers and a writer work at the same time: without it a
        # commit waits for every open read to finish, and a slow one (the
        # audio player streaming a recording) made it fail with "database
        # is locked". The mode is stored in the file, so setting it once
        # here covers every connection, iter_audio's included.
        conn.execute("PRAGMA journal_mode=WAL")
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
        _migrate_users_otp_locked_column(conn)
        _migrate_users_approval_notice_column(conn)
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
                created_at TEXT NOT NULL,
                duration_seconds INTEGER
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_meetings_user "
            "ON meetings(user_id, created_at DESC)"
        )
        _migrate_meetings_mindmap_column(conn)
        _migrate_meetings_duration_column(conn)
        _create_meeting_results_table(conn)
        _create_meeting_audio_table(conn)
        _create_doctor_tables(conn)


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


def _migrate_users_otp_locked_column(conn):
    """
    Adds `otp_locked`: 1 once an account's verification is in admin hands
    (it has been verified at least once, or an admin created/unverified it).
    From then on the self-service OTP endpoints refuse the account, so an
    admin's "unverify" can't be undone by the user emailing themselves a
    fresh code.

    Also folds the retired active/inactive `status` into verification:
    inactive accounts become unverified + locked, so they stay blocked
    until an admin verifies them. The `status` column itself is left in
    place (unused) rather than dropped.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "otp_locked" in existing:
        return

    conn.execute("ALTER TABLE users ADD COLUMN otp_locked INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE users SET otp_locked = 1 WHERE email_verified = 1")
    conn.execute(
        "UPDATE users SET email_verified = 0, otp_locked = 1, status = 'active' "
        "WHERE status = 'inactive'"
    )


def _migrate_users_approval_notice_column(conn):
    """
    Adds `approval_notice_pending`: set to 1 when an admin verifies an
    unverified account, cleared on that user's next successful sign-in so
    the "your account was approved" notice shows exactly once.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "approval_notice_pending" in existing:
        return

    conn.execute("ALTER TABLE users ADD COLUMN approval_notice_pending INTEGER NOT NULL DEFAULT 0")


def _migrate_meetings_mindmap_column(conn):
    """Adds mindmap_json to a `meetings` table created before it existed."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(meetings)")}
    if "mindmap_json" in existing:
        return

    conn.execute("ALTER TABLE meetings ADD COLUMN mindmap_json TEXT")


def _migrate_meetings_duration_column(conn):
    """
    Adds duration_seconds — how long the recording ran — to a `meetings`
    table created before it existed. Meetings saved before this have no
    duration and stay NULL.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(meetings)")}
    if "duration_seconds" in existing:
        return

    conn.execute("ALTER TABLE meetings ADD COLUMN duration_seconds INTEGER")


def _create_meeting_results_table(conn):
    """
    One row per (meeting, LLM) pair: the summary and mind map that model
    produced for that meeting. The composite primary key is what keeps a
    meeting from ever holding two results for the same model — generating
    again, or hand-edits, update that row in place.

    The first time this table is created on an existing database, every
    meeting's legacy meetings.summary_json / meetings.mindmap_json is
    copied in as a "mistral" result, since Mistral was the only model
    before results were stored per model. Those legacy columns are left
    untouched (as a pre-migration snapshot) and are no longer read or
    written by the app.
    """
    already_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meeting_results'"
    ).fetchone()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meeting_results (
            meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            summary_json TEXT,
            mindmap_json TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (meeting_id, model)
        )
    """)

    if already_exists:
        return

    conn.execute(
        "INSERT INTO meeting_results (meeting_id, model, summary_json, mindmap_json, updated_at) "
        "SELECT id, 'mistral', summary_json, mindmap_json, created_at FROM meetings "
        "WHERE summary_json IS NOT NULL OR mindmap_json IS NOT NULL"
    )


# Columns shared by meeting_audio, doctor_audio and interview_audio
# (interview_database.py). The parent id is the
# INTEGER PRIMARY KEY, so it is also the row's rowid — which is what
# sqlite3's incremental blob I/O (Connection.blobopen) needs to stream a
# byte range without loading the whole recording into memory.
_AUDIO_COLUMNS = """
    audio BLOB NOT NULL,
    mime_type TEXT NOT NULL,
    file_ext TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    source TEXT NOT NULL,
    original_filename TEXT,
    created_at TEXT NOT NULL
"""


def _create_meeting_audio_table(conn):
    """
    The recording behind a meeting (live or uploaded), one per meeting.
    Kept out of `meetings` so listing meetings never reads audio bytes.
    """
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS meeting_audio (
            meeting_id INTEGER PRIMARY KEY REFERENCES meetings(id) ON DELETE CASCADE,
            {_AUDIO_COLUMNS}
        )
    """)


def _create_doctor_tables(conn):
    """
    Everything the Doctor–Patient template stores. Deliberately separate
    from meetings / meeting_results / meeting_audio, so consultations never
    show up in (or alter) meeting history, and vice versa.

    doctor_profiles       one letterhead per user (logo/signature as BLOBs)
    doctor_consultations  one per recorded/uploaded consultation
    doctor_audio          that consultation's recording
    doctor_prescriptions  the prescription for a consultation: the fields
                          meeting_intelligence.DOCTOR_PRESCRIPTION_FIELDS
                          produces, the untouched AI draft, and whether the
                          doctor has finalised (downloaded) it
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS doctor_profiles (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            doctor_name TEXT NOT NULL,
            qualifications TEXT NOT NULL DEFAULT '',
            specialization TEXT NOT NULL DEFAULT '',
            clinic_name TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            timings TEXT NOT NULL DEFAULT '',
            logo BLOB,
            logo_mime TEXT,
            signature BLOB,
            signature_mime TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS doctor_consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            transcript TEXT NOT NULL,
            duration_seconds INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_doctor_consultations_user "
        "ON doctor_consultations(user_id, created_at DESC)"
    )
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS doctor_audio (
            consultation_id INTEGER PRIMARY KEY
                REFERENCES doctor_consultations(id) ON DELETE CASCADE,
            {_AUDIO_COLUMNS}
        )
    """)
    text_columns = ",\n".join(
        f"            {name} TEXT NOT NULL DEFAULT ''" for name in PRESCRIPTION_TEXT_FIELDS
    )
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS doctor_prescriptions (
            consultation_id INTEGER PRIMARY KEY
                REFERENCES doctor_consultations(id) ON DELETE CASCADE,
            model TEXT,
{text_columns},
            medicines_json TEXT NOT NULL DEFAULT '[]',
            ai_draft_json TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finalized_at TEXT
        )
    """)


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


def create_user(username, email, password_hash, role="user", email_verified=0, otp_locked=0):
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at, email_verified, otp_locked) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, email, password_hash, role, created_at, email_verified, otp_locked),
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
    """On startup, make sure at least one admin can sign in; create or repair admin@gmail.com if not."""
    if any(u["role"] == "admin" and u["email_verified"] for u in list_users()):
        return

    existing = get_user_by_email("admin@gmail.com")
    if existing:
        update_user(existing["id"], role="admin", email_verified=1, otp_locked=1)
        return

    create_user(
        username="admin",
        email="admin@gmail.com",
        password_hash=password_hash,
        role="admin",
        email_verified=1,
        otp_locked=1,
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


def delete_sessions_for_user(user_id):
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# ============================================================
# MEETINGS
# ============================================================

def find_or_create_meeting(user_id, transcript, title="Untitled Meeting", within_hours=6,
                           duration_seconds=None):
    """
    The id of this user's most recent meeting holding exactly this
    transcript, creating that meeting if there is none. A newly created
    meeting records `duration_seconds`, the length of its recording.

    /api/meeting/summarize and /api/meeting/mindmap open the meeting row
    lazily, once per model, so a "generate with every model" click sends
    several requests for the same recording at once — none of which
    knows about the row another has just inserted. Looking the recording
    up by its own transcript lets every one of them land on the same row,
    and BEGIN IMMEDIATE takes SQLite's write lock before that lookup, so
    two requests can't both miss the row and both insert it. The time
    window keeps an unrelated old meeting that happens to share a very
    short transcript out of it.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=within_hours)
    ).isoformat()

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM meetings "
            "WHERE user_id = ? AND transcript = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, transcript, cutoff),
        ).fetchone()
        if row:
            return row["id"]

        cur = conn.execute(
            "INSERT INTO meetings (user_id, title, transcript, created_at, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, title, transcript, datetime.now(timezone.utc).isoformat(), duration_seconds),
        )
        return cur.lastrowid


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
    """Patch the title (or any column) on an existing meeting."""
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
        "meetings.duration_seconds, "
        "EXISTS (SELECT 1 FROM meeting_results r WHERE r.meeting_id = meetings.id "
        "AND r.summary_json IS NOT NULL) AS has_summary, "
        "EXISTS (SELECT 1 FROM meeting_results r WHERE r.meeting_id = meetings.id "
        "AND r.mindmap_json IS NOT NULL) AS has_mindmap, "
        # "model:SM" per model with a result — S/M are 1/0 for summary/mind map.
        "(SELECT GROUP_CONCAT(r.model || ':' || (r.summary_json IS NOT NULL) "
        "|| (r.mindmap_json IS NOT NULL)) FROM meeting_results r "
        "WHERE r.meeting_id = meetings.id) AS result_models, "
        "LENGTH(meetings.transcript) AS transcript_chars, "
        "EXISTS (SELECT 1 FROM meeting_audio a WHERE a.meeting_id = meetings.id) AS has_audio, "
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


# ============================================================
# PER-MODEL RESULTS
# ============================================================

def get_meeting_results(meeting_id):
    """{model: {"summary_json": ..., "mindmap_json": ...}} for one meeting."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT model, summary_json, mindmap_json FROM meeting_results WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchall()
        return {
            row["model"]: {
                "summary_json": row["summary_json"],
                "mindmap_json": row["mindmap_json"],
            }
            for row in rows
        }


def save_meeting_result(meeting_id, model, **fields):
    """
    Upsert one model's result for a meeting. Only the columns passed
    (summary_json and/or mindmap_json) are written, so saving a mind map
    never clears that model's summary and vice versa.
    """
    allowed = {"summary_json", "mindmap_json"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unknown meeting_results columns: {sorted(unknown)}")
    if not fields:
        return

    updated_at = datetime.now(timezone.utc).isoformat()
    columns = list(fields)
    assignments = ", ".join(f"{col} = excluded.{col}" for col in columns)

    with _connect() as conn:
        conn.execute(
            f"INSERT INTO meeting_results (meeting_id, model, {', '.join(columns)}, updated_at) "
            f"VALUES (?, ?, {', '.join('?' for _ in columns)}, ?) "
            f"ON CONFLICT(meeting_id, model) DO UPDATE SET {assignments}, "
            "updated_at = excluded.updated_at",
            [meeting_id, model, *fields.values(), updated_at],
        )


# ============================================================
# RECORDINGS (meeting_audio / doctor_audio / interview_audio)
# ============================================================

def _audio_table(table):
    if table not in _AUDIO_TABLES:
        raise ValueError(f"Unknown audio table: {table}")
    return table, _AUDIO_TABLES[table]


def save_audio(table, parent_id, data, mime_type, file_ext, source, original_filename=None):
    """Store (or replace) the recording for one meeting / consultation."""
    table, key = _audio_table(table)
    with _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({key}, audio, mime_type, file_ext, size_bytes, "
            "source, original_filename, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parent_id,
                sqlite3.Binary(data),
                mime_type,
                file_ext,
                len(data),
                source,
                original_filename,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def get_audio_meta(table, parent_id):
    """Everything about a stored recording except its bytes, or None."""
    table, key = _audio_table(table)
    with _connect() as conn:
        row = conn.execute(
            f"SELECT mime_type, file_ext, size_bytes, source, original_filename, created_at "
            f"FROM {table} WHERE {key} = ?",
            (parent_id,),
        ).fetchone()
        return dict(row) if row else None


def iter_audio(table, parent_id, start, end, chunk_size=256 * 1024):
    """
    Yield the bytes [start, end] (inclusive) of a stored recording in
    chunks, for HTTP range responses (seeking in the audio player).
    Uses incremental blob I/O where the sqlite3 module has it (Python
    3.11+), else SQL substr() per chunk — either way the whole recording
    is never held in memory at once.

    Each chunk is read and its read finished before it is yielded, so no
    lock is held while the generator waits on a slow client. The browser's
    <audio> element often reads a little and then stalls the request; a
    blob handle kept open across those yields used to hold the database's
    read lock the whole time and block every commit behind it.
    """
    table, key = _audio_table(table)
    # StreamingResponse advances this generator one chunk at a time on
    # whichever threadpool worker is free, so the connection must be
    # usable from any thread. Calls never overlap (each chunk is awaited
    # before the next is requested), so sharing it this way is safe.
    # Without this, any recording larger than one chunk broke off mid-
    # download ("Failed - Network error" / "Check internet connection").
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        position = start
        while position <= end:
            length = min(chunk_size, end - position + 1)
            if hasattr(conn, "blobopen"):
                with conn.blobopen(table, "audio", parent_id, readonly=True) as blob:
                    blob.seek(position)
                    data = blob.read(length)
            else:
                rows = conn.execute(
                    f"SELECT substr(audio, ?, ?) FROM {table} WHERE {key} = ?",
                    (position + 1, length, parent_id),
                ).fetchall()
                data = bytes(rows[0][0]) if rows and rows[0][0] else b""
            if not data:
                break
            position += len(data)
            yield data
    finally:
        conn.close()


# ============================================================
# DOCTOR PROFILES
# ============================================================

# Passed instead of image bytes to clear a stored logo/signature.
REMOVE_IMAGE = object()


def get_doctor_profile(user_id):
    """The user's letterhead details (no image bytes), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, " + ", ".join(DOCTOR_PROFILE_TEXT_FIELDS) + ", "
            "logo IS NOT NULL AS has_logo, signature IS NOT NULL AS has_signature, "
            "created_at, updated_at FROM doctor_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        profile = dict(row)
        profile["has_logo"] = bool(profile["has_logo"])
        profile["has_signature"] = bool(profile["has_signature"])
        return profile


def get_doctor_profile_image(user_id, kind):
    """(bytes, mime) for the user's "logo" or "signature", or None."""
    if kind not in ("logo", "signature"):
        raise ValueError(f"Unknown profile image: {kind}")
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {kind} AS data, {kind}_mime AS mime FROM doctor_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row or row["data"] is None:
            return None
        return bytes(row["data"]), row["mime"] or "application/octet-stream"


def save_doctor_profile(user_id, fields, logo=None, signature=None):
    """
    Upsert the user's letterhead. `fields` holds the text columns. `logo`
    and `signature` are each None (keep what is stored), REMOVE_IMAGE
    (clear it), or a (bytes, mime) pair (replace it).
    """
    now = datetime.now(timezone.utc).isoformat()
    values = {name: (fields.get(name) or "").strip() for name in DOCTOR_PROFILE_TEXT_FIELDS}

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute(
            "SELECT 1 FROM doctor_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if exists:
            assignments = ", ".join(f"{name} = ?" for name in values)
            conn.execute(
                f"UPDATE doctor_profiles SET {assignments}, updated_at = ? WHERE user_id = ?",
                [*values.values(), now, user_id],
            )
        else:
            columns = ", ".join(values)
            marks = ", ".join("?" for _ in values)
            conn.execute(
                f"INSERT INTO doctor_profiles (user_id, {columns}, created_at, updated_at) "
                f"VALUES (?, {marks}, ?, ?)",
                [user_id, *values.values(), now, now],
            )

        for kind, image in (("logo", logo), ("signature", signature)):
            if image is None:
                continue
            if image is REMOVE_IMAGE:
                conn.execute(
                    f"UPDATE doctor_profiles SET {kind} = NULL, {kind}_mime = NULL WHERE user_id = ?",
                    (user_id,),
                )
            else:
                data, mime = image
                conn.execute(
                    f"UPDATE doctor_profiles SET {kind} = ?, {kind}_mime = ? WHERE user_id = ?",
                    (sqlite3.Binary(data), mime, user_id),
                )

    return get_doctor_profile(user_id)


# ============================================================
# DOCTOR CONSULTATIONS
# ============================================================

def find_or_create_consultation(user_id, transcript, title="Untitled consultation",
                                within_hours=6, duration_seconds=None):
    """
    The id of this user's most recent consultation holding exactly this
    transcript, creating it if there is none. Same reasoning (and the
    same write lock) as find_or_create_meeting().
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=within_hours)
    ).isoformat()

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM doctor_consultations "
            "WHERE user_id = ? AND transcript = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, transcript, cutoff),
        ).fetchone()
        if row:
            return row["id"]

        cur = conn.execute(
            "INSERT INTO doctor_consultations (user_id, title, transcript, created_at, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, title, transcript, datetime.now(timezone.utc).isoformat(), duration_seconds),
        )
        return cur.lastrowid


def get_consultation(consultation_id):
    """Full record with the owner's id/username/email, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT c.*, users.username AS username, users.email AS email "
            "FROM doctor_consultations c JOIN users ON users.id = c.user_id "
            "WHERE c.id = ?",
            (consultation_id,),
        ).fetchone()
        return dict(row) if row else None


def update_consultation(consultation_id, **fields):
    if not fields:
        return get_consultation(consultation_id)
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [consultation_id]
    with _connect() as conn:
        conn.execute(f"UPDATE doctor_consultations SET {columns} WHERE id = ?", values)
    return get_consultation(consultation_id)


def list_consultations(user_id=None):
    """
    Newest first; every user's when `user_id` is None (admin view). Only
    the headline fields — no transcript or audio bytes.
    """
    query = (
        "SELECT c.id, c.title, c.created_at, c.user_id, c.duration_seconds, "
        "LENGTH(c.transcript) AS transcript_chars, "
        "p.patient_name, p.age_sex, p.diagnosis, p.status AS prescription_status, "
        "p.updated_at AS prescription_updated_at, p.finalized_at, "
        "a.size_bytes AS audio_bytes, "
        "users.username AS username, users.email AS email "
        "FROM doctor_consultations c "
        "JOIN users ON users.id = c.user_id "
        "LEFT JOIN doctor_prescriptions p ON p.consultation_id = c.id "
        "LEFT JOIN doctor_audio a ON a.consultation_id = c.id "
    )
    params = ()
    if user_id is not None:
        query += "WHERE c.user_id = ? "
        params = (user_id,)
    query += "ORDER BY c.created_at DESC"

    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


# ============================================================
# DOCTOR PRESCRIPTIONS
# ============================================================

def get_prescription(consultation_id):
    """The consultation's prescription with `medicines` decoded, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM doctor_prescriptions WHERE consultation_id = ?",
            (consultation_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["medicines"] = json.loads(data.pop("medicines_json") or "[]")
        except ValueError:
            data["medicines"] = []
        data.pop("ai_draft_json", None)
        return data


def save_prescription(consultation_id, prescription, status="draft", model=None, ai_draft=None):
    """
    Upsert a consultation's prescription. `prescription` holds the text
    fields and `medicines`. A fresh AI draft (status "draft") also records
    the model and the untouched draft; the doctor's edited copy saved on
    download (status "final") stamps finalized_at and leaves those alone.
    """
    if status not in ("draft", "final"):
        raise ValueError(f"Unknown prescription status: {status}")

    now = datetime.now(timezone.utc).isoformat()
    text = {
        name: str(prescription.get(name) or "").strip()
        for name in PRESCRIPTION_TEXT_FIELDS
    }
    medicines = prescription.get("medicines")
    medicines_json = json.dumps(medicines if isinstance(medicines, list) else [], ensure_ascii=False)

    columns = {**text, "medicines_json": medicines_json, "status": status, "updated_at": now}
    if model is not None:
        columns["model"] = model
    if ai_draft is not None:
        columns["ai_draft_json"] = json.dumps(ai_draft, ensure_ascii=False)
    columns["finalized_at"] = now if status == "final" else None

    names = list(columns)
    assignments = ", ".join(f"{name} = excluded.{name}" for name in names)

    with _connect() as conn:
        conn.execute(
            f"INSERT INTO doctor_prescriptions (consultation_id, {', '.join(names)}, created_at) "
            f"VALUES (?, {', '.join('?' for _ in names)}, ?) "
            f"ON CONFLICT(consultation_id) DO UPDATE SET {assignments}",
            [consultation_id, *columns.values(), now],
        )
    return get_prescription(consultation_id)