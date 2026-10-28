"""

MeetMind FastAPI application.

Browser -> /ws/meeting -> meeting_websocket.py -> Complete WAV recording

-> Parrotlet-A 2.5 Pro -> Complete transcript -> Frontend

-> POST /api/meeting/summarize {model} -> meeting_intelligence.py

-> Mistral 128B API / Qwen3-27B API -> Structured Meeting Intelligence

Mind Map flow:

Frontend transcript

-> POST /api/meeting/mindmap {model}

-> meeting_intelligence.py

-> Mistral 128B API / Qwen3-27B API

-> Hierarchical Mind Map JSON

Each model's summary and mind map are stored separately per meeting

(database.py's meeting_results table). The available models are listed

in LLM_MODELS below and served to the frontend by GET /api/models.

Speaker diarization: Disabled

"""

import json

import io

import wave

import logging

import shutil

import subprocess

import uuid

import re

import mimetypes

from pathlib import Path

from typing import Any, List, Optional

from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket

from fastapi.concurrency import run_in_threadpool

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from meeting_websocket import (

    meeting_websocket,

    MODEL_NAME,

    SAMPLE_RATE,

    CHANNELS,

    SAMPLE_WIDTH,

    RECORDINGS_DIR,

    save_wav,

    transcribe_audio,

)

from meeting_intelligence import (

    generate_meeting_summary,

    generate_meeting_summary_qwen,

    generate_mindmap,

    generate_mindmap_qwen,

    generate_doctor_prescription,

    generate_doctor_prescription_qwen,

    MISTRAL_MODEL,

    QWEN_MODEL,

)

import database as db

import auth

import audio_storage

import interview_database as interview_db

# Interview template: its own tables (interview_database.py), routes
# (interview_routes.py, /api/interview/*) and BharatAI Qwen evaluation
# (interview_analysis.py). interview_analysis reads its settings from the
# environment at import time, so .env is loaded first.

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from interview_routes import interview_router

# ============================================================

# LOGGING

# ============================================================

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",

)

logger = logging.getLogger("meetmind")

# ===========================================================

# PATH CONFIGURATION

# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = BASE_DIR.parent

FRONTEND_DIR = PROJECT_ROOT / "frontend"

INDEX_FILE = FRONTEND_DIR / "index.html"

LANDING_FILE = FRONTEND_DIR / "landing.html"

AUTH_FILE = FRONTEND_DIR / "auth.html"

ADMIN_FILE = FRONTEND_DIR / "admin.html"

ASSETS_DIR = FRONTEND_DIR / "assets"

# Where doctor profiles were kept (JSON + images per user) before they
# moved into the database. Only read once, to import them; see
# _import_legacy_doctor_profiles().
LEGACY_DOCTOR_PROFILES_DIR = BASE_DIR / "doctor_profiles"

logger.info(

    "Backend directory: %s",

    BASE_DIR,

)

logger.info(

    "Project root: %s",

    PROJECT_ROOT,

)

logger.info(

    "Frontend directory: %s",

    FRONTEND_DIR,

)

# ============================================================

# FASTAPI APPLICATION

# ============================================================

app = FastAPI(

    title="Vidatha",

    description=(

        "AI powered Intelligence using "

        "Parrotlet-A 2.5 Pro and Mistral 128B"

    ),

    version="3.0.0",

)

# ============================================================

# CORS

# ============================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

# ============================================================

# STARTUP - DATABASE / AUTH INITIALIZATION

# ============================================================

@app.on_event("startup")

def _init_auth():

    db.init_db()

    interview_db.init_db()

    db.ensure_seed_admin(

        auth.hash_password("admin123")

    )

    _import_legacy_doctor_profiles()

# ============================================================

# AUTH ROUTER

# ============================================================

app.include_router(

    auth.router

)

# Interview template: profile, evaluation and saved interviews (/api/interview/*)

app.include_router(

    interview_router

)

# ============================================================

# REQUEST MODELS

# ============================================================

class DoctorPrescriptionRequest(BaseModel):

    transcript: str

    model: str = "mistral"

    # The consultation (doctor_consultations row) the draft is saved to.
    # Without one, the consultation holding this transcript is reused or
    # created, so a generated draft is always saved.
    consultation_id: Optional[int] = None


class PrescriptionSaveRequest(BaseModel):

    # The prescription as the doctor left it: the text fields of
    # DOCTOR_PRESCRIPTION_FIELDS plus `medicines`. Unknown keys are dropped.
    prescription: dict

    # True when saved because the doctor downloaded it (status "final").
    final: bool = True


class SummaryRequest(BaseModel):

    transcript: str

    meeting_id: Optional[int] = None

    # Length of the recording in seconds (from the websocket's

    # final_transcript). Stored on the meeting when this request creates it.

    duration_seconds: Optional[float] = None

    # Select the LLM used for meeting intelligence.

    # Supported values: the keys of LLM_MODELS ("mistral", "qwen").

    model: str = "mistral"

class MindMapRequest(BaseModel):

    transcript: str

    meeting_id: Optional[int] = None

    # Length of the recording in seconds — see SummaryRequest.

    duration_seconds: Optional[float] = None

    # Select the LLM used for mind-map generation.

    # Supported values: the keys of LLM_MODELS ("mistral", "qwen").

    model: str = "mistral"

# Fields the meeting-intelligence editor

# (frontend/index.html) lets an owner hand-edit and save.

#

# All optional: only the keys actually sent are patched.

class MeetingUpdateRequest(BaseModel):

    title: Optional[str] = None

    objective: Optional[str] = None

    meeting_summary: Optional[str] = None

    tasks_assigned: Optional[List[Any]] = None

    decision_points: Optional[List[Any]] = None

    objections: Optional[List[Any]] = None

    action_items: Optional[List[Any]] = None

    mindmap: Optional[Any] = None

    # Which model's result these edits belong to. Defaults to the

    # first entry of LLM_MODELS for clients that predate per-model

    # results.

    model: Optional[str] = None

# ============================================================

# LLM MODEL REGISTRY

# ============================================================

# Every model the frontend can generate with, in display order. The

# first entry is the default and the "primary" model: its summary

# title becomes the meeting's history title. Adding a model here is

# all the frontend needs — it builds its model selector, result

# columns and report options from GET /api/models.

LLM_MODELS = {

    "mistral": {

        "label": "Mistral 128B",

        "model_id": MISTRAL_MODEL,

        "summarize": generate_meeting_summary,

        "mindmap": generate_mindmap,

    },

    "qwen": {

        "label": "Qwen3 27B",

        "model_id": QWEN_MODEL,

        "summarize": generate_meeting_summary_qwen,

        "mindmap": generate_mindmap_qwen,

    },

}

DEFAULT_LLM_MODEL = next(iter(LLM_MODELS))

def _resolve_model(

    name: Optional[str],

) -> str:

    key = (name or DEFAULT_LLM_MODEL).strip().lower()

    if key not in LLM_MODELS:

        raise ValueError(

            "Unsupported model. Use one of: "

            + ", ".join(f"'{k}'" for k in LLM_MODELS)

            + "."

        )

    return key

# ============================================================

# STATIC ASSETS

# ============================================================

# Self-hosted web fonts (frontend/assets/fonts). Python's mimetypes
# table has no entry for .woff2, which would otherwise be served as
# text/plain.
mimetypes.add_type("font/woff2", ".woff2")

if ASSETS_DIR.exists():

    app.mount(

        "/assets",

        StaticFiles(

            directory=ASSETS_DIR

        ),

        name="assets",

    )

# ============================================================

# NO-STALe CACHE MIDDLEWARE

# ============================================================

@app.middleware("http")

async def _no_stale_cache(

    request: Request,

    call_next,

):

    response = await call_next(request)

    path = request.url.path

    if (

        path.startswith("/assets/")

        or not path.startswith("/api/")

    ):

        response.headers[

            "Cache-Control"

        ] = (

            "no-store, "

            "no-cache, "

            "must-revalidate"

        )

        response.headers[

            "Pragma"

        ] = "no-cache"

        response.headers[

            "Expires"

        ] = "0"

    return response
# ============================================================
# SECURITY HEADERS
# ============================================================

@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"

    # Enforced policy. The frontend has no inline scripts, inline styles
    # or third-party hosts (fonts and jsPDF / html2canvas / lottie are
    # self-hosted under /assets). The one style hash is the fixed
    # <style> block html2canvas injects into its document clone to hide
    # pseudo-elements during PDF export; it must be recomputed if
    # assets/vendor/html2canvas.min.js is ever upgraded.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'sha256-UP0QZg7irvSMvOBz9mH2PIIE28+57UiavRfeVea0l3g='; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )

    return response

# ============================================================

# FRONTEND FILE SERVING

# ============================================================

def _serve(page: Path) -> FileResponse:

    if not page.exists():

        raise HTTPException(

            status_code=404,

            detail=(

                f"Frontend file not found: {page}"

            ),

        )

    return FileResponse(

        page,

        media_type="text/html",

    )

# ============================================================

# HOME

# ============================================================

@app.get("/")

async def home():

    return _serve(

        LANDING_FILE

    )

# ============================================================

# MEETMIND APP

# ============================================================

@app.get("/app")

async def app_view(

    request: Request,

):

    # Admins land on /admin by default

    # but can still open the recorder.

    user = auth.get_current_user(

        request

    )

    if not user:

        # Keep the query (e.g. ?template=doctor from the

        # landing page) so sign-in returns to the same view.

        next_path = "/app"

        if request.url.query:

            next_path += "?" + request.url.query

        return RedirectResponse(

            url="/sign-in?next=" + quote(next_path, safe="/")

        )

    return _serve(

        INDEX_FILE

    )

# ============================================================

# AUTH REDIRECT

# ============================================================

def _redirect_if_already_signed_in(

    request: Request,

):

    user = auth.get_current_user(

        request

    )

    if user:

        # Honour ?next= like the sign-in form does after signing

        # in (e.g. the landing page's "Try this template" links),

        # but only for same-origin paths.

        next_path = request.query_params.get("next", "")

        if (

            not next_path.startswith("/")

            or next_path.startswith("//")

            or "\\" in next_path

        ):

            next_path = auth.landing_path_for_role(

                user["role"]

            )

        return RedirectResponse(

            url=next_path

        )

    return None

# ============================================================

# SIGN IN

# ============================================================

@app.get("/sign-in")

async def sign_in_view(

    request: Request,

):

    return (

        _redirect_if_already_signed_in(

            request

        )

        or _serve(AUTH_FILE)

    )

# ============================================================

# SIGN UP

# ============================================================

@app.get("/sign-up")

async def sign_up_view(

    request: Request,

):

    return (

        _redirect_if_already_signed_in(

            request

        )

        or _serve(AUTH_FILE)

    )

# ============================================================

# VERIFY EMAIL (OTP)

# ============================================================

@app.get("/verify-otp")

async def verify_otp_view(

    request: Request,

):

    return (

        _redirect_if_already_signed_in(

            request

        )

        or _serve(AUTH_FILE)

    )

# ============================================================

# ACCOUNT PENDING (unverified, waiting on an admin)

# ============================================================

@app.get("/account-pending")

async def account_pending_view(

    request: Request,

):

    return (

        _redirect_if_already_signed_in(

            request

        )

        or _serve(AUTH_FILE)

    )

# ============================================================

# ADMIN

# ============================================================

@app.get("/admin")

async def admin_view(

    request: Request,

):

    user = auth.get_current_user(

        request

    )

    if not user:

        return RedirectResponse(

            url="/sign-in?next=/admin"

        )

    if user["role"] != "admin":

        return RedirectResponse(

            url="/app"

        )

    return _serve(

        ADMIN_FILE

    )

# ============================================================

# HEALTH

# ============================================================

@app.get("/health")

async def health():

    return {

        "status": "healthy",

        "service": "Vidatha",

        "speech_model": MODEL_NAME,

        "llm_model": {

            "mistral": MISTRAL_MODEL,

            "qwen": QWEN_MODEL,

        },

        "llm_models": {

            "mistral": MISTRAL_MODEL,

            "qwen": QWEN_MODEL,

        },

        "sample_rate": SAMPLE_RATE,

        "speaker_diarization": False,

    }

# ============================================================

# API INFO

# ============================================================

@app.get("/api/info")

async def api_info():

    return {

        "project": "Vidatha",

        "version": "3.0.0",

        "pipeline": [

            "Browser microphone",

            "PCM16 mono 16 kHz",

            "Complete meeting recording",

            "Parrotlet-A 2.5 Pro",

            "Complete transcript",

            "User requests summary",

            "Mistral 128B API / Qwen3-27B API",

            "Meeting intelligence",

        ],

        "speech_to_text": MODEL_NAME,

        "sample_rate": SAMPLE_RATE,

        "llm": {

            "mistral": MISTRAL_MODEL,

            "qwen": QWEN_MODEL,

        },

        "llm_models": {

            "mistral": MISTRAL_MODEL,

            "qwen": QWEN_MODEL,

        },

        "speaker_diarization": False,

        "processing_mode": "record_then_process",

        "websocket": "/ws/meeting",

        "summary_endpoint": "/api/meeting/summarize",

    }

# ============================================================

# AVAILABLE LLM MODELS

# ============================================================

@app.get("/api/models")

async def list_models():

    """The generation models, in display order (see LLM_MODELS)."""

    return [

        {

            "key": key,

            "label": entry["label"],

            "modelId": entry["model_id"],

        }

        for key, entry in LLM_MODELS.items()

    ]

# ============================================================

# MEETING ROW HELPER

# ============================================================

def _model_tags(

    flags: dict,

) -> list:

    """

    [{key, label, hasSummary, hasMindmap}] for the models that have a

    result, in LLM_MODELS order (then any model no longer offered).

    `flags` maps model key -> (has_summary, has_mindmap). This is what

    the history drawer and admin page show as each meeting's tags.

    """

    order = (

        [key for key in LLM_MODELS if key in flags]

        + [key for key in flags if key not in LLM_MODELS]

    )

    return [

        {

            "key": key,

            "label": LLM_MODELS.get(key, {}).get("label", key),

            "hasSummary": bool(flags[key][0]),

            "hasMindmap": bool(flags[key][1]),

        }

        for key in order

    ]

def _meeting_row(

    row: dict,

) -> dict:

    # db.list_meetings() packs each model as "model:SM" (S/M = 1/0).

    flags = {}

    for part in (row.get("result_models") or "").split(","):

        if ":" in part:

            key, bits = part.rsplit(":", 1)

            flags[key] = (bits[:1] == "1", bits[1:2] == "1")

    return {

        "id": row["id"],

        "title": row["title"],

        "createdAt": row["created_at"],

        "durationSeconds": row["duration_seconds"],

        "hasSummary": bool(

            row["has_summary"]

        ),

        "hasMindmap": bool(

            row["has_mindmap"]

        ),

        "models": _model_tags(

            flags

        ),

        "transcriptChars": (

            row["transcript_chars"]

            or 0

        ),

        "hasAudio": bool(row.get("has_audio")),

        "username": row["username"],

        "email": row["email"],

    }

# ============================================================

# LIST MEETINGS

# ============================================================

@app.get("/api/meetings")

async def list_meetings(

    request: Request,

    scope: str = "mine",

):

    user = auth.require_user(

        request

    )

    if scope == "all":

        if user["role"] != "admin":

            raise HTTPException(

                status_code=403,

                detail="Admin access required.",

            )

        rows = db.list_meetings()

    else:

        rows = db.list_meetings(

            user_id=user["id"]

        )

    return [

        _meeting_row(row)

        for row in rows

    ]

# ============================================================

# MEETING ACCESS / PAYLOAD HELPERS

# ============================================================

def _require_meeting_access(

    meeting_id: int,

    user: dict,

) -> dict:

    meeting = db.get_meeting(

        meeting_id

    )

    if not meeting:

        raise HTTPException(

            status_code=404,

            detail="Meeting not found.",

        )

    if (

        meeting["user_id"] != user["id"]

        and user["role"] != "admin"

    ):

        raise HTTPException(

            status_code=403,

            detail=(

                "You don't have access "

                "to that meeting."

            ),

        )

    return meeting

def _load_json(

    value,

):

    if not value:

        return None

    try:

        return json.loads(

            value

        )

    except ValueError:

        return None

def _ordered_results(

    meeting_id: int,

) -> dict:

    """

    {model: {"summary": ..., "mindmap": ...}} for every model that has a

    result for this meeting. LLM_MODELS order first, then any model no

    longer in the registry, so its saved results stay visible.

    """

    raw = db.get_meeting_results(

        meeting_id

    )

    order = (

        [key for key in LLM_MODELS if key in raw]

        + [key for key in raw if key not in LLM_MODELS]

    )

    results = {}

    for key in order:

        summary = _load_json(

            raw[key]["summary_json"]

        )

        mindmap = _load_json(

            raw[key]["mindmap_json"]

        )

        if summary is None and mindmap is None:

            continue

        results[key] = {

            "summary": summary,

            "mindmap": mindmap,

        }

    return results

def _meeting_payload(

    meeting: dict,

) -> dict:

    results = _ordered_results(

        meeting["id"]

    )

    # `summary` / `mindmap` are the pre-multi-model fields, still read by

    # the admin page: the first model (in LLM_MODELS order) that has each.

    summary = next(

        (r["summary"] for r in results.values() if r["summary"]),

        None,

    )

    mindmap = next(

        (r["mindmap"] for r in results.values() if r["mindmap"]),

        None,

    )

    return {

        "id": meeting["id"],

        "title": meeting["title"],

        "createdAt": meeting["created_at"],

        "durationSeconds": meeting["duration_seconds"],

        "transcript": meeting["transcript"],

        "results": results,

        "models": _model_tags(

            {

                key: (

                    result["summary"] is not None,

                    result["mindmap"] is not None,

                )

                for key, result in results.items()

            }

        ),

        "summary": summary,

        "mindmap": mindmap,

        **audio_storage.audio_fields(
            "meeting_audio",
            meeting["id"],
            f"/api/meetings/{meeting['id']}/audio",
        ),

        "username": meeting["username"],

        "email": meeting["email"],

    }

def _sync_meeting_title(

    meeting_id: int,

) -> None:

    """

    The history title follows the summary title of the first model (in

    LLM_MODELS order) that has a summary, so generating or editing a

    second model's summary never renames the meeting out from under the

    primary one. With no summary at all the title is left as it is

    ("Untitled Meeting", or whatever the mind-map editor set it to).

    """

    for result in _ordered_results(meeting_id).values():

        title = (

            (result["summary"] or {}).get("title")

            or ""

        ).strip()

        if title:

            db.update_meeting(

                meeting_id,

                title=title,

            )

            return

# ============================================================

# GET SINGLE MEETING

# ============================================================

@app.get("/api/meetings/{meeting_id}")

async def get_meeting(

    meeting_id: int,

    request: Request,

):

    user = auth.require_user(

        request

    )

    meeting = _require_meeting_access(

        meeting_id,

        user,

    )

    return _meeting_payload(

        meeting

    )

# ============================================================
# RECORDING PLAYBACK (meeting_audio / doctor_audio)
# ============================================================
# Streaming (with HTTP Range support) lives in audio_storage.py, shared
# with the Interview template's routes (interview_routes.py).

@app.get("/api/meetings/{meeting_id}/audio")
async def get_meeting_audio(meeting_id: int, request: Request):
    """The meeting's stored recording (owner or admin)."""
    user = auth.require_user(request)
    _require_meeting_access(meeting_id, user)
    return audio_storage.audio_response(request, "meeting_audio", meeting_id, f"meeting_{meeting_id}")

# ============================================================

# UPDATE MEETING

# ============================================================

@app.patch(

    "/api/meetings/{meeting_id}"

)

async def update_meeting(

    meeting_id: int,

    request: MeetingUpdateRequest,

    http_request: Request,

):

    """

    Persists hand-edits made in one model's meeting-intelligence editor

    or mind-map editor (frontend/index.html's "Save Changes" buttons).

    Only the owner or an admin may edit.

    The transcript itself is never touched here.

    """

    user = auth.require_user(

        http_request

    )

    _require_meeting_access(

        meeting_id,

        user,

    )

    try:

        model = _resolve_model(

            request.model

        )

    except ValueError as exc:

        raise HTTPException(

            status_code=400,

            detail=str(exc),

        )

    updates = request.dict(

        exclude_unset=True

    )

    updates.pop("model", None)

    # Mind maps are a nested tree, not a flat set of fields — persist them

    # to their own column instead of merging into the summary dict.

    mindmap_included = "mindmap" in updates

    mindmap = updates.pop("mindmap", None)

    # The title may come from either editor. Sent alongside real summary

    # fields (the summary editor), it is this model's summary title. Sent

    # alone (the mind-map editor), it may only name the meeting while no

    # model has a summary yet — after that the summaries own the title.

    title = updates.pop("title", None)

    existing = db.get_meeting_results(

        meeting_id

    ).get(model, {})

    fields = {}

    if updates:

        summary = _load_json(

            existing.get("summary_json")

        ) or {}

        summary.update(

            updates

        )

        if title:

            summary["title"] = title

        fields["summary_json"] = json.dumps(

            summary

        )

    if mindmap_included:

        fields["mindmap_json"] = (

            json.dumps(mindmap)

            if mindmap is not None

            else None

        )

    db.save_meeting_result(

        meeting_id,

        model,

        **fields,

    )

    if updates:

        _sync_meeting_title(

            meeting_id

        )

    elif title and not any(

        result["summary"]

        for result in _ordered_results(meeting_id).values()

    ):

        db.update_meeting(

            meeting_id,

            title=title,

        )

    return _meeting_payload(

        db.get_meeting(meeting_id)

    )

# ============================================================
# DOCTOR / CLINIC PROFILE
# ============================================================

# One letterhead per user, stored in the doctor_profiles table (logo and
# signature as BLOBs). It is printed on every prescription that user makes.

DOCTOR_PROFILE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
DOCTOR_PROFILE_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


async def _read_doctor_profile_image(
    upload: Optional[UploadFile], field_name: str
) -> Optional[tuple]:
    """Validate an optional uploaded profile image; (bytes, mime) or None."""
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in DOCTOR_PROFILE_IMAGE_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a PNG, JPG, JPEG, or WEBP image.",
        )
    data = await upload.read(DOCTOR_PROFILE_IMAGE_MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"{field_name} is empty.")
    if len(data) > DOCTOR_PROFILE_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"{field_name} must not exceed 5 MB.")
    return data, DOCTOR_PROFILE_IMAGE_MIME[suffix]


def _doctor_profile_payload(profile: Optional[dict]) -> Optional[dict]:
    """The profile as the frontend uses it, with URLs for its images."""
    if not profile:
        return None
    payload = {name: profile[name] for name in db.DOCTOR_PROFILE_TEXT_FIELDS}
    version = re.sub(r"[^0-9]", "", profile["updated_at"])
    for kind in ("logo", "signature"):
        payload[f"{kind}_url"] = (
            f"/api/doctor/profile/{kind}?user_id={profile['user_id']}&v={version}"
            if profile[f"has_{kind}"]
            else None
        )
    payload["updated_at"] = profile["updated_at"]
    return payload


def _profile_owner_id(user: dict, user_id: Optional[int]) -> int:
    """Whose profile a request means: your own, or (admins) anyone's."""
    if user_id is None or user_id == user["id"]:
        return user["id"]
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_id


def _import_legacy_doctor_profiles() -> None:
    """
    Copy profiles saved by the earlier file-based version
    (doctor_profiles/<user_id>.json + <user_id>/logo.* / signature.*) into
    the doctor_profiles table, once: a user who already has a database
    profile is skipped, so later edits are never overwritten. The files
    themselves are left alone.
    """
    if not LEGACY_DOCTOR_PROFILES_DIR.is_dir():
        return
    for path in sorted(LEGACY_DOCTOR_PROFILES_DIR.glob("*.json")):
        try:
            user_id = int(path.stem)
            if db.get_doctor_profile(user_id) or not db.get_user_by_id(user_id):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not (data.get("doctor_name") or "").strip():
                continue
            images = {}
            for kind in ("logo", "signature"):
                name = data.get(kind)
                if not name:
                    continue
                image_path = LEGACY_DOCTOR_PROFILES_DIR / str(user_id) / Path(name).name
                mime = DOCTOR_PROFILE_IMAGE_MIME.get(image_path.suffix.lower())
                if mime and image_path.is_file():
                    images[kind] = (image_path.read_bytes(), mime)
            db.save_doctor_profile(user_id, data, **images)
            logger.info("Imported legacy doctor profile %s into the database.", path.name)
        except Exception:
            logger.exception("Could not import legacy doctor profile %s.", path.name)


@app.get("/api/doctor/profile")
async def get_doctor_profile(request: Request, user_id: Optional[int] = None):
    """The signed-in user's doctor/clinic profile (admins: any user's)."""
    user = auth.require_user(request)
    owner_id = _profile_owner_id(user, user_id)
    return {"success": True, "profile": _doctor_profile_payload(db.get_doctor_profile(owner_id))}


@app.get("/api/doctor/profile/{kind}")
async def get_doctor_profile_image(kind: str, request: Request, user_id: Optional[int] = None):
    """The profile's logo or signature image."""
    if kind not in ("logo", "signature"):
        raise HTTPException(status_code=404, detail="Not found.")
    user = auth.require_user(request)
    image = db.get_doctor_profile_image(_profile_owner_id(user, user_id), kind)
    if not image:
        raise HTTPException(status_code=404, detail=f"No {kind} is saved.")
    data, mime = image
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/doctor/profile")
async def save_doctor_profile(
    request: Request,
    doctor_name: str = Form(...),
    qualifications: str = Form(""),
    specialization: str = Form(""),
    clinic_name: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    timings: str = Form(""),
    logo: Optional[UploadFile] = File(None),
    signature: Optional[UploadFile] = File(None),
    remove_logo: bool = Form(False),
    remove_signature: bool = Form(False),
):
    """Save the authenticated user's doctor/clinic profile and optional images."""
    user = auth.require_user(request)
    doctor_name = doctor_name.strip()
    if not doctor_name:
        raise HTTPException(status_code=400, detail="Doctor name is required.")

    try:
        logo_image = await _read_doctor_profile_image(logo, "Logo")
        signature_image = await _read_doctor_profile_image(signature, "Signature")
    finally:
        if logo is not None:
            await logo.close()
        if signature is not None:
            await signature.close()

    profile = db.save_doctor_profile(
        user["id"],
        {
            "doctor_name": doctor_name,
            "qualifications": qualifications,
            "specialization": specialization,
            "clinic_name": clinic_name,
            "address": address,
            "phone": phone,
            "email": email,
            "timings": timings,
        },
        logo=logo_image or (db.REMOVE_IMAGE if remove_logo else None),
        signature=signature_image or (db.REMOVE_IMAGE if remove_signature else None),
    )

    logger.info("Doctor profile saved for user_id=%s", user["id"])
    return {
        "success": True,
        "message": "Doctor profile saved.",
        "profile": _doctor_profile_payload(profile),
    }


# ============================================================

# MEETING WEBSOCKET

# ============================================================

@app.websocket("/ws/meeting")

async def websocket_endpoint(

    websocket: WebSocket,

):

    # The session cookie arrives with the WebSocket handshake, so the
    # finished recording can be saved to this user's history (see
    # _store_recording). Signed-out sockets still transcribe; nothing is saved.
    user = auth.get_current_user(websocket)

    async def persist(*, template, audio_path, transcript, duration):
        return await run_in_threadpool(
            _store_recording,
            user,
            template,
            audio_path,
            source="live",
            transcript=transcript,
            duration=duration,
        )

    await meeting_websocket(

        websocket,

        persist=persist,

    )

# ============================================================

# TEST WEBSOCKET

# ============================================================

@app.websocket("/ws/test")

async def websocket_test(

    websocket: WebSocket,

):

    logger.info(

        "Test websocket handler reached."

    )

    await websocket.accept()

    logger.info(

        "Test websocket accepted."

    )

    await websocket.send_text(

        "TEST_OK"

    )

    await websocket.close()

# ============================================================

# RESULT SAVE TARGET

# ============================================================

def _resolve_meeting_for_save(

    user: dict,

    meeting_id: Optional[int],

    transcript: str,

    duration_seconds: Optional[float] = None,

) -> Optional[int]:

    """

    The meeting row a freshly generated result is saved to, or None to

    skip saving. `duration_seconds` (the recording's length) is stored

    only when this call creates the row.

    An id sent by the client must belong to the user (or the user must be

    an admin). An invalid one drops the save rather than falling back to

    a new row, which would silently duplicate the meeting.

    Without an id, this recording has either no row yet, or one that a

    request still in flight (another model, or the other of summary /

    mind map) has just opened. db.find_or_create_meeting() joins that row

    by transcript instead of logging the same meeting a second time.

    """

    if meeting_id:

        existing = db.get_meeting(

            meeting_id

        )

        if existing and (

            existing["user_id"] == user["id"]

            or user["role"] == "admin"

        ):

            return meeting_id

        return None

    return db.find_or_create_meeting(

        user["id"],

        transcript,

        duration_seconds=(

            round(duration_seconds)

            if duration_seconds and duration_seconds > 0

            else None

        ),

    )

# ============================================================

# ============================================================

# UPLOAD AUDIO NORMALIZATION

# ============================================================

def normalize_audio(input_path: Path, output_path: Path) -> Path:

    """Normalize uploaded audio to mono, 16 kHz, signed 16-bit PCM WAV."""

    ffmpeg_path = shutil.which("ffmpeg")

    if not ffmpeg_path:

        raise RuntimeError(

            "FFmpeg is not installed or is not available in PATH. "

            "Install FFmpeg on the Vidatha backend server and restart the app."

        )

    command = [

        ffmpeg_path,

        "-nostdin",

        "-hide_banner",

        "-loglevel", "error",

        "-y",

        "-i", str(input_path),

        "-map", "0:a:0",

        "-vn",

        "-ac", "1",

        "-ar", str(SAMPLE_RATE),

        "-c:a", "pcm_s16le",

        "-f", "wav",

        str(output_path),

    ]

    result = subprocess.run(

        command,

        capture_output=True,

        text=True,

        check=False,

    )

    if result.returncode != 0:

        try:

            output_path.unlink(missing_ok=True)

        except OSError:

            logger.warning("Could not remove failed normalized audio: %s", output_path)

        error_detail = (result.stderr or "").strip()

        raise RuntimeError(

            "Audio normalization failed: "

            + (error_detail[-1500:] or "Unknown FFmpeg error")

        )

    if not output_path.exists() or output_path.stat().st_size <= 44:

        raise RuntimeError("Audio normalization produced an empty or invalid WAV file.")

    logger.info(

        "Audio normalized: %s -> %s (%d bytes)",

        input_path.name,

        output_path.name,

        output_path.stat().st_size,

    )

    return output_path

# ============================================================
# SAVING A FINISHED RECORDING
# ============================================================

def _template_of(value: Optional[str]) -> str:
    """"doctor" / "interview" for those templates, else "meeting"."""
    value = (value or "").strip().lower()
    return value if value in ("doctor", "interview") else "meeting"


# Per template: the audio table and the key its saved id is returned under.
_TEMPLATE_STORAGE = {
    "meeting": ("meeting_audio", "meeting_id"),
    "doctor": ("doctor_audio", "consultation_id"),
    "interview": ("interview_audio", "interview_id"),
}


def _store_recording(
    user: Optional[dict],
    template: Optional[str],
    audio_path: Path,
    *,
    source: str,
    transcript: str,
    duration: Optional[float],
    original_filename: Optional[str] = None,
) -> dict:
    """
    Save a transcribed recording — live or uploaded — to the history of the
    template it was made in: a meeting (meetings + meeting_audio), a
    consultation (doctor_consultations + doctor_audio) or an interview
    (interviews + interview_audio). They never share rows. Returns the id
    it was saved under and whether the audio made it:

        {"template": "meeting", "meeting_id": 12, "has_audio": True}
        {"template": "doctor", "consultation_id": 4, "has_audio": True}
        {"template": "interview", "interview_id": 7, "has_audio": True}

    Once the audio is in the database the file on disk is deleted; if
    storing it fails, the file is kept so the recording isn't lost.
    Nothing is saved without a signed-in user or a transcript.
    """
    template = _template_of(template)
    if not user or not transcript:
        return {"template": template}

    duration_seconds = round(duration) if duration and duration > 0 else None

    if template == "doctor":
        parent_id = db.find_or_create_consultation(
            user["id"], transcript, duration_seconds=duration_seconds
        )
    elif template == "interview":
        parent_id = interview_db.find_or_create_interview(
            user["id"], transcript, duration_seconds=duration_seconds
        )
    else:
        parent_id = db.find_or_create_meeting(
            user["id"], transcript, duration_seconds=duration_seconds
        )
    table, id_key = _TEMPLATE_STORAGE[template]
    saved = {"template": template, id_key: parent_id}

    try:
        data, mime_type, file_ext = audio_storage.prepare_for_storage(audio_path)
        db.save_audio(table, parent_id, data, mime_type, file_ext, source, original_filename)
        saved["has_audio"] = True
    except Exception:
        logger.exception("Could not store the %s recording %s in the database.", source, audio_path)
        saved["has_audio"] = False
        return saved

    try:
        Path(audio_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Stored recording but could not remove %s", audio_path)

    logger.info(
        "Recording stored | %s=%s | %s | %d bytes",
        id_key,
        parent_id,
        file_ext,
        len(data),
    )
    return saved

# ============================================================

# NETWORK-RESILIENT RECORDING UPLOAD

# ============================================================

@app.post("/api/meeting/upload-recording")

async def upload_recording(

    request: Request,

    audio: UploadFile = File(...),

    # "doctor" saves it as a consultation, "interview" as an interview;
    # anything else as a meeting.
    template: str = Form("meeting"),

):

    """Upload an existing audio recording and transcribe it with Parrotlet."""

    user = auth.require_user(request)

    max_upload_bytes = 500 * 1024 * 1024

    allowed_extensions = {

        ".wav", ".mp3", ".m4a", ".aac", ".flac", ".mpeg",".ogg", ".opus", ".webm", ".mp4"

    }

    original_name = audio.filename or "recording.wav"

    suffix = Path(original_name).suffix.lower()

    if suffix not in allowed_extensions:

        raise HTTPException(

            status_code=400,

            detail="Unsupported audio format. Supported formats: WAV, MP3, M4A, AAC, FLAC, MPEG, OGG, OPUS, WEBM, and MP4.",

        )

    upload_id = uuid.uuid4().hex

    audio_path = RECORDINGS_DIR / f"upload_{upload_id}{suffix}"

    normalized_path = RECORDINGS_DIR / f"upload_{upload_id}_normalized.wav"

    total_bytes = 0

    duration = None

    try:

        # Stream the upload to disk in bounded chunks; never read a 500 MB file

        # into one Python bytes object. The size check is based on actual bytes,

        # not only the browser-provided Content-Length or MIME type.

        with audio_path.open("wb") as output:

            while True:

                chunk = await audio.read(1024 * 1024)

                if not chunk:

                    break

                total_bytes += len(chunk)

                if total_bytes > max_upload_bytes:

                    raise HTTPException(

                        status_code=413,

                        detail="Recording exceeds the maximum upload size of 500 MB.",

                    )

                output.write(chunk)

        if total_bytes == 0:

            raise HTTPException(status_code=400, detail="Uploaded recording is empty.")

        logger.info(

            "Recording uploaded: %s | bytes=%d | user_id=%s",

            audio_path.name,

            total_bytes,

            user["id"],

        )

        # Normalize every uploaded format before sending it to Parrotlet.

        # The live WebSocket recording path remains unchanged.

        await run_in_threadpool(

            normalize_audio,

            audio_path,

            normalized_path,

        )

        logger.info(

            "Starting Parrotlet transcription on normalized audio: %s",

            normalized_path.name,

        )

        transcription = await run_in_threadpool(

            transcribe_audio,

            str(normalized_path),

        )

        if not isinstance(transcription, dict):

            raise RuntimeError("The transcription pipeline returned an invalid result.")

        transcript = (transcription.get("text") or "").strip()

        duration_value = transcription.get("duration")

        if duration_value is not None:

            try:

                duration = float(duration_value)

            except (TypeError, ValueError):

                duration = None

        # Saves the transcript to the template's history and the upload
        # itself as that item's recording (then deletes it from disk).
        saved = await run_in_threadpool(
            _store_recording,
            user,
            template,
            audio_path,
            source="upload",
            transcript=transcript,
            duration=duration,
            original_filename=Path(original_name).name,
        )

        logger.info(

            "Uploaded recording transcription complete | saved=%s | transcript_chars=%d | duration=%s",

            saved,

            len(transcript),

            f"{duration:.2f}" if duration is not None else "unknown",

        )

        return {

            "success": True,

            "template": saved["template"],

            "meeting_id": saved.get("meeting_id"),

            "consultation_id": saved.get("consultation_id"),

            "interview_id": saved.get("interview_id"),

            "has_audio": saved.get("has_audio", False),

            "transcript": transcript,

            "segments": transcription.get("segments", []),

            "duration": duration,

            "speech_model": MODEL_NAME,

            "speaker_diarization": False,

            "final": True,

        }

    except HTTPException:

        # Delete rejected/failed partial uploads, but preserve completed recordings.

        if audio_path.exists():

            try:

                audio_path.unlink()

            except OSError:

                logger.warning("Could not remove partial upload %s", audio_path)

        raise

    except Exception as exc:

        if audio_path.exists():

            try:

                audio_path.unlink()

            except OSError:

                logger.warning("Could not remove failed upload %s", audio_path)

        logger.exception("Uploaded recording processing failed.")

        raise HTTPException(status_code=500, detail=f"Recording transcription failed: {exc}")

    finally:

        await audio.close()

        if normalized_path.exists():

            try:

                normalized_path.unlink()

            except OSError:

                logger.warning(

                    "Could not remove normalized audio file: %s",

                    normalized_path,

                )

# ============================================================
# DOCTOR PRESCRIPTION DRAFT
# ============================================================

@app.post("/api/doctor/prescription")
async def create_doctor_prescription(request: DoctorPrescriptionRequest, http_request: Request):
    """
    Generate a draft prescription separately from MOM summary and mindmap,
    and save it to the consultation (status "draft") for a signed-in user.
    """
    transcript = (request.transcript or "").strip()
    if not transcript:
        return {"success": False, "error": "Transcript is empty."}

    model = (request.model or "mistral").strip().lower()
    generators = {
        "mistral": (generate_doctor_prescription, MISTRAL_MODEL),
        "qwen": (generate_doctor_prescription_qwen, QWEN_MODEL),
    }
    if model not in generators:
        raise HTTPException(status_code=400, detail="Unsupported prescription model. Use mistral or qwen.")

    generator, model_id = generators[model]
    try:
        prescription = await run_in_threadpool(generator, transcript)
    except Exception as exc:
        logger.exception("Doctor prescription draft generation failed (%s).", model)
        return {"success": False, "error": str(exc)}

    user = auth.get_current_user(http_request)

    # Use the signed-in user's saved doctor name only as profile metadata; do not
    # overwrite a doctor name extracted from the consultation if one is present.
    try:
        if user and not prescription.get("doctor_name"):
            profile = db.get_doctor_profile(user["id"])
            if profile:
                prescription["doctor_name"] = profile["doctor_name"]
    except Exception:
        logger.debug("Doctor profile could not be applied to prescription draft.", exc_info=True)

    consultation_id = None
    if user:
        try:
            consultation_id = _resolve_consultation_for_save(
                user, request.consultation_id, transcript
            )
            if consultation_id:
                db.save_prescription(
                    consultation_id,
                    prescription,
                    status="draft",
                    model=model,
                    ai_draft=prescription,
                )
                _sync_consultation_title(consultation_id, prescription)
        except Exception:
            logger.exception("Could not save the prescription draft to the consultation.")

    return {"success": True, "model": model, "model_id": model_id, "prescription": prescription,
            "consultation_id": consultation_id, "status": "draft", "review_required": True}


# ============================================================
# DOCTOR CONSULTATIONS (history of the Doctor–Patient template)
# ============================================================

_MEDICINE_FIELDS = ("medicine", "dose", "route", "frequency", "duration", "instructions")


def _resolve_consultation_for_save(
    user: dict, consultation_id: Optional[int], transcript: str
) -> Optional[int]:
    """
    The consultation a prescription is saved to, or None to skip saving.
    Mirrors _resolve_meeting_for_save(): a client-sent id must be the
    user's own (or the user an admin); without one, the consultation
    holding this transcript is reused or created.
    """
    if consultation_id:
        existing = db.get_consultation(consultation_id)
        if existing and (existing["user_id"] == user["id"] or user["role"] == "admin"):
            return consultation_id
        return None
    return db.find_or_create_consultation(user["id"], transcript)


def _sync_consultation_title(consultation_id: int, prescription: dict) -> None:
    """A consultation is listed under its patient's name once one is known."""
    name = str(prescription.get("patient_name") or "").strip()
    if name:
        db.update_consultation(consultation_id, title=name[:200])


def _require_consultation_access(consultation_id: int, user: dict) -> dict:
    consultation = db.get_consultation(consultation_id)
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found.")
    if consultation["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You don't have access to that consultation.")
    return consultation


def _clean_prescription(data: dict) -> dict:
    """Only the known prescription fields, every value a trimmed string."""
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Prescription must be an object.")
    cleaned = {
        name: str(data.get(name) or "").strip()[:5000]
        for name in db.PRESCRIPTION_TEXT_FIELDS
    }
    medicines = []
    for item in data.get("medicines") or []:
        if not isinstance(item, dict):
            continue
        medicine = {field: str(item.get(field) or "").strip()[:500] for field in _MEDICINE_FIELDS}
        if any(medicine.values()):
            medicines.append(medicine)
    cleaned["medicines"] = medicines
    return cleaned


def _prescription_payload(prescription: Optional[dict]) -> Optional[dict]:
    if not prescription:
        return None
    payload = {name: prescription[name] for name in db.PRESCRIPTION_TEXT_FIELDS}
    payload["medicines"] = prescription["medicines"]
    model = prescription.get("model")
    payload.update({
        "status": prescription["status"],
        "model": model,
        "modelLabel": LLM_MODELS.get(model, {}).get("label", model) if model else None,
        "createdAt": prescription["created_at"],
        "updatedAt": prescription["updated_at"],
        "finalizedAt": prescription["finalized_at"],
    })
    return payload


def _consultation_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "patientName": row["patient_name"] or "",
        "ageSex": row["age_sex"] or "",
        "diagnosis": row["diagnosis"] or "",
        "createdAt": row["created_at"],
        "durationSeconds": row["duration_seconds"],
        "transcriptChars": row["transcript_chars"] or 0,
        "hasAudio": row["audio_bytes"] is not None,
        "prescriptionStatus": row["prescription_status"],
        "prescriptionUpdatedAt": row["prescription_updated_at"],
        "finalizedAt": row["finalized_at"],
        "userId": row["user_id"],
        "username": row["username"],
        "email": row["email"],
    }


def _consultation_payload(consultation: dict) -> dict:
    return {
        "id": consultation["id"],
        "title": consultation["title"],
        "createdAt": consultation["created_at"],
        "durationSeconds": consultation["duration_seconds"],
        "transcript": consultation["transcript"],
        "prescription": _prescription_payload(db.get_prescription(consultation["id"])),
        **audio_storage.audio_fields(
            "doctor_audio",
            consultation["id"],
            f"/api/doctor/consultations/{consultation['id']}/audio",
        ),
        # The letterhead belongs to whoever recorded the consultation, so an
        # admin viewing it sees that doctor's letterhead, not their own.
        "doctorProfile": _doctor_profile_payload(db.get_doctor_profile(consultation["user_id"])),
        "userId": consultation["user_id"],
        "username": consultation["username"],
        "email": consultation["email"],
    }


@app.get("/api/doctor/consultations")
async def list_consultations(request: Request, scope: str = "mine"):
    """The user's consultations, newest first (admins: scope=all for everyone's)."""
    user = auth.require_user(request)
    if scope == "all":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        rows = db.list_consultations()
    else:
        rows = db.list_consultations(user_id=user["id"])
    return [_consultation_row(row) for row in rows]


@app.get("/api/doctor/consultations/{consultation_id}")
async def get_consultation(consultation_id: int, request: Request):
    user = auth.require_user(request)
    return _consultation_payload(_require_consultation_access(consultation_id, user))


@app.get("/api/doctor/consultations/{consultation_id}/audio")
async def get_consultation_audio(consultation_id: int, request: Request):
    user = auth.require_user(request)
    _require_consultation_access(consultation_id, user)
    return audio_storage.audio_response(
        request, "doctor_audio", consultation_id, f"consultation_{consultation_id}"
    )


@app.put("/api/doctor/consultations/{consultation_id}/prescription")
async def save_consultation_prescription(
    consultation_id: int, request: PrescriptionSaveRequest, http_request: Request
):
    """
    Save the prescription as the doctor edited it. The frontend calls this
    when the prescription is downloaded, which marks it "final".
    """
    user = auth.require_user(http_request)
    _require_consultation_access(consultation_id, user)
    prescription = _clean_prescription(request.prescription)
    saved = db.save_prescription(
        consultation_id,
        prescription,
        status="final" if request.final else "draft",
    )
    _sync_consultation_title(consultation_id, prescription)
    logger.info(
        "Prescription saved | consultation_id=%s | status=%s | user_id=%s",
        consultation_id,
        saved["status"],
        user["id"],
    )
    return {"success": True, "prescription": _prescription_payload(saved)}


# ============================================================

# CREATE SUMMARY

# ============================================================

@app.post(

    "/api/meeting/summarize"

)

async def create_summary(

    request: SummaryRequest,

    http_request: Request,

):

    transcript = (

        request.transcript or ""

    ).strip()

    logger.info(

        "Received meeting summarization request (model: %s).",

        request.model,

    )

    logger.info(

        "Transcript length: %d characters",

        len(transcript),

    )

    if not transcript:

        return {

            "success": False,

            "error": "Transcript is empty.",

        }

    try:

        model = _resolve_model(

            request.model

        )

        entry = LLM_MODELS[model]

        logger.info(

            "Generating meeting intelligence using %s: %s",

            entry["label"],

            entry["model_id"],

        )

        # The generators are blocking HTTP calls. Running them on the

        # thread pool lets the other models' requests (and every other

        # endpoint) proceed while this model is still answering.

        result = await run_in_threadpool(

            entry["summarize"],

            transcript,

        )

        logger.info(

            "Meeting intelligence generated successfully."

        )

    except Exception as exc:

        logger.exception(

            "Summary generation failed."

        )

        return {

            "success": False,

            "error": str(exc),

        }

    # --------------------------------------------------------

    # SUMMARY PAYLOAD

    # --------------------------------------------------------

    payload = {

        "success": True,

        "model": model,

        "title": result.get(

            "title",

            "Untitled Meeting",

        ),

        "objective": result.get(

            "objective",

            "",

        ),

        "meeting_summary": result.get(

            "meeting_summary",

            "",

        ),

        "tasks_assigned": result.get(

            "tasks_assigned",

            [],

        ),

        "decision_points": result.get(

            "decision_points",

            [],

        ),

        "objections": result.get(

            "objections",

            [],

        ),

        "action_items": result.get(

            "action_items",

            [],

        ),

        "timeline": result.get(

            "timeline",

            [],

        ),

    }

    # --------------------------------------------------------

    # SAVE SUMMARY TO DATABASE (this model's result row)

    # --------------------------------------------------------

    user = auth.get_current_user(

        http_request

    )

    if user:

        try:

            meeting_id = _resolve_meeting_for_save(

                user,

                request.meeting_id,

                transcript,

                request.duration_seconds,

            )

            if meeting_id:

                db.save_meeting_result(

                    meeting_id,

                    model,

                    summary_json=json.dumps(

                        payload

                    ),

                )

                _sync_meeting_title(

                    meeting_id

                )

                payload[

                    "meeting_id"

                ] = meeting_id

        except Exception as exc:

            logger.exception(

                "Could not save meeting to history: %s",

                exc,

            )

    return payload

# ============================================================

# CREATE MIND MAP

# ============================================================

@app.post(

    "/api/meeting/mindmap"

)

async def create_mindmap(

    request: MindMapRequest,

    http_request: Request,

):

    transcript = (

        request.transcript or ""

    ).strip()

    logger.info(

        "Received meeting mind-map generation request (model: %s).",

        request.model,

    )

    logger.info(

        "Transcript length: %d characters",

        len(transcript),

    )

    # --------------------------------------------------------

    # EMPTY TRANSCRIPT

    # --------------------------------------------------------

    if not transcript:

        return {

            "success": False,

            "error": "Transcript is empty.",

        }

    # --------------------------------------------------------

    # GENERATE MIND MAP

    # --------------------------------------------------------

    try:

        model = _resolve_model(

            request.model

        )

        entry = LLM_MODELS[model]

        logger.info(

            "Generating mind map using %s: %s",

            entry["label"],

            entry["model_id"],

        )

        mindmap = await run_in_threadpool(

            entry["mindmap"],

            transcript,

        )

        logger.info(

            "Mind map generated successfully."

        )

    except Exception as exc:

        logger.exception(

            "Mind-map generation failed."

        )

        return {

            "success": False,

            "error": str(exc),

        }

    payload = {

        "success": True,

        "model": model,

        "mindmap": mindmap,

    }

    # --------------------------------------------------------

    # SAVE MIND MAP TO DATABASE (best-effort, this model's row)

    # --------------------------------------------------------

    user = auth.get_current_user(

        http_request

    )

    if user:

        try:

            meeting_id = _resolve_meeting_for_save(

                user,

                request.meeting_id,

                transcript,

                request.duration_seconds,

            )

            if meeting_id:

                db.save_meeting_result(

                    meeting_id,

                    model,

                    mindmap_json=json.dumps(

                        mindmap

                    ),

                )

                # Echo it back the way create_summary() does, so the

                # client can trust this field rather than having to

                # remember what it sent.

                payload[

                    "meeting_id"

                ] = meeting_id

        except Exception as exc:

            logger.exception(

                "Could not save mind map to history: %s",

                exc,

            )

    return payload

# ============================================================

# STARTUP LOGGING

# ============================================================

@app.on_event("startup")

async def startup_event():

    logger.info(

        "=" * 70

    )

    logger.info(

        "VIDATHA BACKEND STARTED"

    )

    logger.info(

        "=" * 70

    )

    logger.info(

        "LLM models: %s",

        ", ".join(

            f"{key} ({entry['label']}: {entry['model_id']})"

            for key, entry in LLM_MODELS.items()

        ),

    )

    logger.info(

        "ASR model: %s",

        MODEL_NAME,

    )

    logger.info(

        "Sample rate: %s Hz",

        SAMPLE_RATE,

    )

    logger.info(

        "Speaker diarization: DISABLED"

    )

    logger.info(

        "WebSocket endpoint: /ws/meeting"

    )

    logger.info(

        "WebSocket diagnostic endpoint: /ws/test"

    )

    logger.info(

        "Summary endpoint: /api/meeting/summarize"

    )

    logger.info(

        "Mind-map endpoint: /api/meeting/mindmap"

    )

    logger.info(

        "Frontend directory: %s",

        FRONTEND_DIR,

    )

    logger.info(

        "=" * 70

    )

# ============================================================

# SHUTDOWN

# ============================================================

@app.on_event("shutdown")

async def shutdown_event():

    logger.info(

        "Vidatha backend shutting down."

    )
