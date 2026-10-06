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

import logging

from pathlib import Path

from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket

from fastapi.concurrency import run_in_threadpool

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse, RedirectResponse

from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from meeting_websocket import (

    meeting_websocket,

    MODEL_NAME,

    SAMPLE_RATE,

)

from meeting_intelligence import (

    generate_meeting_summary,

    generate_meeting_summary_qwen,

    generate_mindmap,

    generate_mindmap_qwen,

    MISTRAL_MODEL,

    QWEN_MODEL,

)

import database as db

import auth

# ============================================================

# LOGGING

# ============================================================

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",

)

logger = logging.getLogger("meetmind")

# ============================================================

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

    title="MeetMind",

    description=(

        "AI Meeting Intelligence using "

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

    db.ensure_seed_admin(

        auth.hash_password("admin123")

    )

# ============================================================

# AUTH ROUTER

# ============================================================

app.include_router(

    auth.router

)

# ============================================================

# REQUEST MODELS

# ============================================================

class SummaryRequest(BaseModel):

    transcript: str

    meeting_id: Optional[int] = None

    # Select the LLM used for meeting intelligence.

    # Supported values: the keys of LLM_MODELS ("mistral", "qwen").

    model: str = "mistral"

class MindMapRequest(BaseModel):

    transcript: str

    meeting_id: Optional[int] = None

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

        return RedirectResponse(

            url="/sign-in?next=/app"

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

        return RedirectResponse(

            url=auth.landing_path_for_role(

                user["role"]

            )

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

        "service": "MeetMind",

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

        "project": "MeetMind",

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

# MEETING WEBSOCKET

# ============================================================

@app.websocket("/ws/meeting")

async def websocket_endpoint(

    websocket: WebSocket,

):

    await meeting_websocket(

        websocket

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

) -> Optional[int]:

    """

    The meeting row a freshly generated result is saved to, or None to

    skip saving.


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

    )

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

        "MEETMIND BACKEND STARTED"

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

        "MeetMind backend shutting down."

    )
