"""
MeetMind FastAPI application.

Browser -> /ws/meeting -> meeting_websocket.py -> Complete WAV recording
-> Parrotlet-A 2.5 Pro -> Complete transcript -> Frontend
-> POST /api/meeting/summarize -> meeting_intelligence.py -> mistral_client.py
-> Mistral 128B API -> Structured Meeting Intelligence

Mind Map flow:

Frontend transcript
-> POST /api/meeting/mindmap
-> meeting_intelligence.py
-> Mistral 128B API
-> Hierarchical Mind Map JSON

Speaker diarization: Disabled
"""

import json
import logging
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket
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
    generate_mindmap,
    MISTRAL_MODEL,
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


class MindMapRequest(BaseModel):
    transcript: str
    meeting_id: Optional[int] = None


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
        "llm_model": MISTRAL_MODEL,
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
            "Mistral 128B API",
            "Meeting intelligence",
        ],
        "speech_to_text": MODEL_NAME,
        "sample_rate": SAMPLE_RATE,
        "llm": MISTRAL_MODEL,
        "speaker_diarization": False,
        "processing_mode": "record_then_process",
        "websocket": "/ws/meeting",
        "summary_endpoint": "/api/meeting/summarize",
    }


# ============================================================
# MEETING ROW HELPER
# ============================================================

def _meeting_row(
    row: dict,
) -> dict:

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

    summary = None

    if meeting["summary_json"]:

        try:

            summary = json.loads(
                meeting["summary_json"]
            )

        except ValueError:

            summary = None

    mindmap = None

    if meeting["mindmap_json"]:

        try:

            mindmap = json.loads(
                meeting["mindmap_json"]
            )

        except ValueError:

            mindmap = None

    return {
        "id": meeting["id"],
        "title": meeting["title"],
        "createdAt": meeting["created_at"],
        "transcript": meeting["transcript"],
        "summary": summary,
        "mindmap": mindmap,
        "username": meeting["username"],
        "email": meeting["email"],
    }


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
    Persists hand-edits made in the meeting-intelligence
    editor (frontend/index.html's "Save Changes" button).

    Only the owner or an admin may edit.

    The transcript itself is never touched here.
    """

    user = auth.require_user(
        http_request
    )

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

    updates = request.dict(
        exclude_unset=True
    )

    # Mind maps are a nested tree, not a flat set of fields — persist them
    # to their own column instead of merging into the summary dict.
    mindmap_included = "mindmap" in updates
    mindmap = updates.pop("mindmap", None)

    # The title is its own column (used for the history list) and may be
    # edited from either the summary editor or the mind-map editor — the
    # latter often has no summary yet, so it's handled separately from the
    # summary-field merge below instead of always requiring one.
    title = updates.pop("title", None)

    fields = {}

    if title:

        fields["title"] = title

    # Only touch summary_json when there are real summary fields to merge,
    # or an existing summary whose title needs to stay in sync — a bare
    # title edit from the mind-map editor shouldn't fabricate a stub
    # summary out of thin air.
    if updates or (
        title and meeting["summary_json"]
    ):

        summary = {}

        if meeting["summary_json"]:

            try:

                summary = json.loads(
                    meeting["summary_json"]
                )

            except ValueError:

                summary = {}

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

    updated = db.update_meeting(
        meeting_id,
        **fields,
    )

    return {
        "id": updated["id"],
        "title": updated["title"],
        "createdAt": updated["created_at"],
        "transcript": updated["transcript"],
        "summary": (
            json.loads(
                updated["summary_json"]
            )
            if updated["summary_json"]
            else None
        ),
        "mindmap": (
            json.loads(
                updated["mindmap_json"]
            )
            if updated["mindmap_json"]
            else None
        ),
        "username": updated["username"],
        "email": updated["email"],
    }


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
        "Received meeting summarization request."
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

        logger.info(
            "Generating meeting intelligence "
            "using Mistral model: %s",
            MISTRAL_MODEL,
        )

        result = generate_meeting_summary(
            transcript
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
    # SAVE SUMMARY TO DATABASE
    # --------------------------------------------------------

    user = auth.get_current_user(
        http_request
    )

    if user:

        try:

            title = (
                payload["title"]
                or "Untitled Meeting"
            )

            if request.meeting_id:

                existing = db.get_meeting(
                    request.meeting_id
                )

                if existing and (
                    existing["user_id"] == user["id"]
                    or user["role"] == "admin"
                ):

                    db.update_meeting(
                        request.meeting_id,
                        title=title,
                        summary_json=json.dumps(
                            payload
                        ),
                    )

                    payload[
                        "meeting_id"
                    ] = request.meeting_id

            if not payload.get("meeting_id"):

                meeting = db.create_meeting(
                    user_id=user["id"],
                    title=title,
                    transcript=transcript,
                    summary_json=json.dumps(
                        payload
                    ),
                )

                payload[
                    "meeting_id"
                ] = meeting["id"]

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
        "Received meeting mind-map generation request."
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

        logger.info(
            "Generating mind map directly from transcript "
            "using Mistral model: %s",
            MISTRAL_MODEL,
        )

        mindmap = generate_mindmap(
            transcript
        )

        logger.info(
            "Mind map generated successfully."
        )

        payload = {
            "success": True,
            "mindmap": mindmap,
        }

        # ----------------------------------------------------
        # SAVE MIND MAP TO DATABASE (best-effort)
        # ----------------------------------------------------

        user = auth.get_current_user(
            http_request
        )

        if user:

            try:

                if request.meeting_id:

                    existing = db.get_meeting(
                        request.meeting_id
                    )

                    if existing and (
                        existing["user_id"] == user["id"]
                        or user["role"] == "admin"
                    ):

                        db.update_meeting(
                            request.meeting_id,
                            mindmap_json=json.dumps(
                                mindmap
                            ),
                        )

                else:

                    meeting = db.create_meeting(
                        user_id=user["id"],
                        title="Untitled Meeting",
                        transcript=transcript,
                        summary_json=None,
                        mindmap_json=json.dumps(
                            mindmap
                        ),
                    )

                    payload[
                        "meeting_id"
                    ] = meeting["id"]

            except Exception as exc:

                logger.exception(
                    "Could not save mind map to history: %s",
                    exc,
                )

        return payload

    except Exception as exc:

        logger.exception(
            "Mind-map generation failed."
        )

        return {
            "success": False,
            "error": str(exc),
        }


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
        "Mistral model: %s",
        MISTRAL_MODEL,
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