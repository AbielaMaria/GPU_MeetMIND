"""
MeetMind — Interview template persistence.

Everything the Interview template stores, in its own tables of
backend/meetmind.db. They are deliberately separate from the meeting
(meetings / meeting_results / meeting_audio) and Doctor–Patient
(doctor_*) tables, so interviews never show up in, or alter, either of
those histories — and vice versa.

    interview_profiles     one letterhead per user: organisation and
                           interviewer details, logo/signature as BLOBs
    interviews             one per recorded/uploaded interview, with the
                           interview setup (candidate, position, type,
                           required skills)
    interview_audio        that interview's recording (columns shared
                           with meeting_audio / doctor_audio, so the
                           generic audio helpers in database.py work)
    interview_evaluations  the evaluation report as the interviewer left
                           it, the untouched AI draft, and whether the
                           interviewer has finalised (downloaded) it

Connections, the audio helpers and the users table come from
database.py; this module only adds the interview tables and queries.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from database import _AUDIO_COLUMNS, _connect

INTERVIEW_PROFILE_TEXT_FIELDS = (
    "organization_name",
    "interviewer_name",
    "designation",
    "department",
    "address",
    "phone",
    "email",
    "website",
)

# The interview setup columns of `interviews`, in form order.
INTERVIEW_SETUP_FIELDS = (
    "candidate_name",
    "interviewer_name",
    "position",
    "interview_type",
)

INTERVIEW_TYPES = ("Technical", "HR", "Behavioral", "Mixed")

# Passed instead of image bytes to clear a stored logo/signature.
REMOVE_IMAGE = object()


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Create the interview tables (idempotent). Called on app startup."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                organization_name TEXT NOT NULL DEFAULT '',
                interviewer_name TEXT NOT NULL,
                designation TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                logo BLOB,
                logo_mime TEXT,
                signature BLOB,
                signature_mime TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                duration_seconds INTEGER,
                candidate_name TEXT NOT NULL DEFAULT '',
                interviewer_name TEXT NOT NULL DEFAULT '',
                position TEXT NOT NULL DEFAULT '',
                interview_type TEXT NOT NULL DEFAULT 'Technical',
                required_skills_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interviews_user "
            "ON interviews(user_id, created_at DESC)"
        )
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS interview_audio (
                interview_id INTEGER PRIMARY KEY
                    REFERENCES interviews(id) ON DELETE CASCADE,
                {_AUDIO_COLUMNS}
            )
        """)
        # report_json is the whole evaluation (Q&A analysis, skill
        # assessment, strengths, conclusion, scoring, the interviewer's own
        # decision). score_percent / total_questions are copied out of it so
        # history listings never have to parse the report.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_evaluations (
                interview_id INTEGER PRIMARY KEY
                    REFERENCES interviews(id) ON DELETE CASCADE,
                model TEXT,
                report_json TEXT NOT NULL,
                ai_draft_json TEXT,
                score_percent INTEGER,
                total_questions INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finalized_at TEXT
            )
        """)


# ============================================================
# INTERVIEWER / ORGANISATION PROFILES
# ============================================================

def get_profile(user_id):
    """The user's interview letterhead (no image bytes), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, " + ", ".join(INTERVIEW_PROFILE_TEXT_FIELDS) + ", "
            "logo IS NOT NULL AS has_logo, signature IS NOT NULL AS has_signature, "
            "created_at, updated_at FROM interview_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        profile = dict(row)
        profile["has_logo"] = bool(profile["has_logo"])
        profile["has_signature"] = bool(profile["has_signature"])
        return profile


def get_profile_image(user_id, kind):
    """(bytes, mime) for the user's "logo" or "signature", or None."""
    if kind not in ("logo", "signature"):
        raise ValueError(f"Unknown profile image: {kind}")
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {kind} AS data, {kind}_mime AS mime FROM interview_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row or row["data"] is None:
            return None
        return bytes(row["data"]), row["mime"] or "application/octet-stream"


def save_profile(user_id, fields, logo=None, signature=None):
    """
    Upsert the user's interview letterhead. `fields` holds the text
    columns. `logo` and `signature` are each None (keep what is stored),
    REMOVE_IMAGE (clear it), or a (bytes, mime) pair (replace it).
    """
    now = _now()
    values = {name: (fields.get(name) or "").strip() for name in INTERVIEW_PROFILE_TEXT_FIELDS}

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute(
            "SELECT 1 FROM interview_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if exists:
            assignments = ", ".join(f"{name} = ?" for name in values)
            conn.execute(
                f"UPDATE interview_profiles SET {assignments}, updated_at = ? WHERE user_id = ?",
                [*values.values(), now, user_id],
            )
        else:
            columns = ", ".join(values)
            marks = ", ".join("?" for _ in values)
            conn.execute(
                f"INSERT INTO interview_profiles (user_id, {columns}, created_at, updated_at) "
                f"VALUES (?, {marks}, ?, ?)",
                [user_id, *values.values(), now, now],
            )

        for kind, image in (("logo", logo), ("signature", signature)):
            if image is None:
                continue
            if image is REMOVE_IMAGE:
                conn.execute(
                    f"UPDATE interview_profiles SET {kind} = NULL, {kind}_mime = NULL WHERE user_id = ?",
                    (user_id,),
                )
            else:
                data, mime = image
                conn.execute(
                    f"UPDATE interview_profiles SET {kind} = ?, {kind}_mime = ? WHERE user_id = ?",
                    (sqlite3.Binary(data), mime, user_id),
                )

    return get_profile(user_id)


# ============================================================
# INTERVIEWS
# ============================================================

def find_or_create_interview(user_id, transcript, title="Untitled interview",
                             within_hours=6, duration_seconds=None):
    """
    The id of this user's most recent interview holding exactly this
    transcript, creating it if there is none. Same reasoning (and the same
    write lock) as database.find_or_create_meeting().
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM interviews "
            "WHERE user_id = ? AND transcript = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, transcript, cutoff),
        ).fetchone()
        if row:
            return row["id"]

        now = _now()
        cur = conn.execute(
            "INSERT INTO interviews (user_id, title, transcript, duration_seconds, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, transcript, duration_seconds, now, now),
        )
        return cur.lastrowid


def _decode_interview(row):
    data = dict(row)
    try:
        skills = json.loads(data.pop("required_skills_json") or "[]")
    except ValueError:
        skills = []
    data["required_skills"] = [str(s) for s in skills if str(s).strip()] if isinstance(skills, list) else []
    return data


def get_interview(interview_id):
    """Full record with the owner's id/username/email, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT i.*, users.username AS username, users.email AS email "
            "FROM interviews i JOIN users ON users.id = i.user_id "
            "WHERE i.id = ?",
            (interview_id,),
        ).fetchone()
        return _decode_interview(row) if row else None


def update_interview(interview_id, **fields):
    """
    Patch an interview's title and/or setup. `required_skills` is passed
    as a list and stored as JSON; anything else must be a column name.
    """
    allowed = {"title", "required_skills", *INTERVIEW_SETUP_FIELDS}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unknown interview columns: {sorted(unknown)}")
    if not fields:
        return get_interview(interview_id)

    if "required_skills" in fields:
        fields["required_skills_json"] = json.dumps(
            list(fields.pop("required_skills") or []), ensure_ascii=False
        )
    fields["updated_at"] = _now()
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(
            f"UPDATE interviews SET {columns} WHERE id = ?",
            [*fields.values(), interview_id],
        )
    return get_interview(interview_id)


def list_interviews(user_id=None):
    """
    Newest first; every user's when `user_id` is None (admin view). Only
    the headline fields — no transcript, report or audio bytes.
    """
    query = (
        "SELECT i.id, i.title, i.created_at, i.user_id, i.duration_seconds, "
        "i.candidate_name, i.position, i.interview_type, i.required_skills_json, "
        "LENGTH(i.transcript) AS transcript_chars, "
        "e.status AS evaluation_status, e.score_percent, e.total_questions, "
        "e.updated_at AS evaluation_updated_at, e.finalized_at, "
        "a.size_bytes AS audio_bytes, "
        "users.username AS username, users.email AS email "
        "FROM interviews i "
        "JOIN users ON users.id = i.user_id "
        "LEFT JOIN interview_evaluations e ON e.interview_id = i.id "
        "LEFT JOIN interview_audio a ON a.interview_id = i.id "
    )
    params = ()
    if user_id is not None:
        query += "WHERE i.user_id = ? "
        params = (user_id,)
    query += "ORDER BY i.created_at DESC"

    with _connect() as conn:
        return [_decode_interview(r) for r in conn.execute(query, params).fetchall()]


# ============================================================
# EVALUATIONS
# ============================================================

def get_evaluation(interview_id):
    """The interview's evaluation with `report` decoded, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM interview_evaluations WHERE interview_id = ?",
            (interview_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["report"] = json.loads(data.pop("report_json") or "{}")
        except ValueError:
            data["report"] = {}
        data.pop("ai_draft_json", None)
        return data


def save_evaluation(interview_id, report, status="draft", model=None, ai_draft=None):
    """
    Upsert an interview's evaluation. A fresh AI evaluation (status
    "draft") also records the model and the untouched AI draft; the
    interviewer's edited copy saved on download (status "final") stamps
    finalized_at and leaves those alone.
    """
    if status not in ("draft", "final"):
        raise ValueError(f"Unknown evaluation status: {status}")

    now = _now()
    scoring = report.get("scoring") if isinstance(report.get("scoring"), dict) else {}
    columns = {
        "report_json": json.dumps(report, ensure_ascii=False),
        "score_percent": scoring.get("score_percent"),
        "total_questions": int(scoring.get("total_questions") or 0),
        "status": status,
        "updated_at": now,
        "finalized_at": now if status == "final" else None,
    }
    if model is not None:
        columns["model"] = model
    if ai_draft is not None:
        columns["ai_draft_json"] = json.dumps(ai_draft, ensure_ascii=False)

    names = list(columns)
    assignments = ", ".join(f"{name} = excluded.{name}" for name in names)
    if ai_draft is not None:
        # A fresh AI evaluation starts over: created_at == updated_at until
        # the interviewer saves an edit (the frontend reads that difference).
        assignments += ", created_at = excluded.created_at"

    with _connect() as conn:
        conn.execute(
            f"INSERT INTO interview_evaluations (interview_id, {', '.join(names)}, created_at) "
            f"VALUES (?, {', '.join('?' for _ in names)}, ?) "
            f"ON CONFLICT(interview_id) DO UPDATE SET {assignments}",
            [interview_id, *columns.values(), now],
        )
    return get_evaluation(interview_id)
