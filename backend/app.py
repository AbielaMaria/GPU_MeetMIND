"""
MeetMind FastAPI application.

Browser -> /ws/meeting -> meeting_websocket.py -> Complete WAV recording
-> Parrotlet-A 2.5 Pro -> Complete transcript -> Frontend
-> POST /api/meeting/summarize -> meeting_intelligence.py -> mistral_client.py
-> Mistral 128B API -> Structured Meeting Intelligence

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
    MISTRAL_MODEL,
)

import database as db
import auth


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("meetmind")


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

INDEX_FILE = FRONTEND_DIR / "index.html"
LANDING_FILE = FRONTEND_DIR / "landing.html"
AUTH_FILE = FRONTEND_DIR / "auth.html"
ADMIN_FILE = FRONTEND_DIR / "admin.html"
ASSETS_DIR = FRONTEND_DIR / "assets"

logger.info("Backend directory: %s", BASE_DIR)
logger.info("Project root: %s", PROJECT_ROOT)
logger.info("Frontend directory: %s", FRONTEND_DIR)


app = FastAPI(
    title="MeetMind",
    description="AI Meeting Intelligence using Parrotlet-A 2.5 Pro and Mistral 128B",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _init_auth():
    db.init_db()
    db.ensure_seed_admin(auth.hash_password("admin123"))


app.include_router(auth.router)


class SummaryRequest(BaseModel):
    transcript: str


# Fields the meeting-intelligence editor (frontend/index.html) lets an owner
# hand-edit and save. All optional: only the keys actually sent are patched.
class MeetingUpdateRequest(BaseModel):
    title: Optional[str] = None
    objective: Optional[str] = None
    meeting_summary: Optional[str] = None
    tasks_assigned: Optional[List[Any]] = None
    decision_points: Optional[List[Any]] = None
    objections: Optional[List[Any]] = None
    action_items: Optional[List[Any]] = None


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.middleware("http")
async def _no_stale_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/") or not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _serve(page: Path) -> FileResponse:
    if not page.exists():
        raise HTTPException(status_code=404, detail=f"Frontend file not found: {page}")
    return FileResponse(page, media_type="text/html")


@app.get("/")
async def home():
    return _serve(LANDING_FILE)


@app.get("/app")
async def app_view(request: Request):
    # Admins land on /admin by default (see landing_path_for_role), but can
    # still open this page via the admin panel's "Recorder" button — their
    # own recordings are then tracked under their own account, like anyone.
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/sign-in?next=/app")
    return _serve(INDEX_FILE)


def _redirect_if_already_signed_in(request: Request):
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse(url=auth.landing_path_for_role(user["role"]))
    return None


@app.get("/sign-in")
async def sign_in_view(request: Request):
    return _redirect_if_already_signed_in(request) or _serve(AUTH_FILE)


@app.get("/sign-up")
async def sign_up_view(request: Request):
    return _redirect_if_already_signed_in(request) or _serve(AUTH_FILE)


@app.get("/admin")
async def admin_view(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/sign-in?next=/admin")
    if user["role"] != "admin":
        return RedirectResponse(url="/app")
    return _serve(ADMIN_FILE)


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


def _meeting_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "createdAt": row["created_at"],
        "hasSummary": bool(row["has_summary"]),
        "transcriptChars": row["transcript_chars"] or 0,
        "username": row["username"],
        "email": row["email"],
    }


@app.get("/api/meetings")
async def list_meetings(request: Request, scope: str = "mine"):
    user = auth.require_user(request)

    if scope == "all":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        rows = db.list_meetings()
    else:
        rows = db.list_meetings(user_id=user["id"])

    return [_meeting_row(r) for r in rows]


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: int, request: Request):
    user = auth.require_user(request)
    meeting = db.get_meeting(meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    if meeting["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You don't have access to that meeting.")

    summary = None
    if meeting["summary_json"]:
        try:
            summary = json.loads(meeting["summary_json"])
        except ValueError:
            summary = None

    return {
        "id": meeting["id"],
        "title": meeting["title"],
        "createdAt": meeting["created_at"],
        "transcript": meeting["transcript"],
        "summary": summary,
        "username": meeting["username"],
        "email": meeting["email"],
    }


@app.patch("/api/meetings/{meeting_id}")
async def update_meeting(meeting_id: int, request: MeetingUpdateRequest, http_request: Request):
    """
    Persists hand-edits made in the meeting-intelligence editor
    (frontend/index.html's "Save Changes" button). Only the owner (or an
    admin) may edit; the transcript itself is never touched here.
    """
    user = auth.require_user(http_request)
    meeting = db.get_meeting(meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    if meeting["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You don't have access to that meeting.")

    updates = request.dict(exclude_unset=True)

    summary = {}
    if meeting["summary_json"]:
        try:
            summary = json.loads(meeting["summary_json"])
        except ValueError:
            summary = {}
    summary.update(updates)

    fields = {"summary_json": json.dumps(summary)}
    if updates.get("title"):
        fields["title"] = updates["title"]

    updated = db.update_meeting(meeting_id, **fields)

    return {
        "id": updated["id"],
        "title": updated["title"],
        "createdAt": updated["created_at"],
        "transcript": updated["transcript"],
        "summary": json.loads(updated["summary_json"]) if updated["summary_json"] else None,
        "username": updated["username"],
        "email": updated["email"],
    }


@app.websocket("/ws/meeting")
async def websocket_endpoint(websocket: WebSocket):
    await meeting_websocket(websocket)


@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    logger.info("Test websocket handler reached.")
    await websocket.accept()
    logger.info("Test websocket accepted.")
    await websocket.send_text("TEST_OK")
    await websocket.close()


@app.post("/api/meeting/summarize")
async def create_summary(request: SummaryRequest, http_request: Request):
    transcript = (request.transcript or "").strip()

    logger.info("Received meeting summarization request.")
    logger.info("Transcript length: %d characters", len(transcript))

    if not transcript:
        return {"success": False, "error": "Transcript is empty."}

    try:
        logger.info("Generating meeting intelligence using Mistral model: %s", MISTRAL_MODEL)
        result = generate_meeting_summary(transcript)
        logger.info("Meeting intelligence generated successfully.")
    except Exception as exc:
        logger.exception("Summary generation failed.")
        return {"success": False, "error": str(exc)}

    payload = {
        "success": True,
        "title": result.get("title", "Untitled Meeting"),
        "objective": result.get("objective", ""),
        "meeting_summary": result.get("meeting_summary", ""),
        "tasks_assigned": result.get("tasks_assigned", []),
        "decision_points": result.get("decision_points", []),
        "objections": result.get("objections", []),
        "action_items": result.get("action_items", []),
        "timeline": result.get("timeline", []),
    }

    user = auth.get_current_user(http_request)
    if user:
        try:
            meeting = db.create_meeting(
                user_id=user["id"],
                title=payload["title"] or "Untitled Meeting",
                transcript=transcript,
                summary_json=json.dumps(payload),
            )
            payload["meeting_id"] = meeting["id"]
        except Exception as exc:
            logger.exception("Could not save meeting to history: %s", exc)

    return payload


@app.on_event("startup")
async def startup_event():
    logger.info("=" * 70)
    logger.info("MEETMIND BACKEND STARTED")
    logger.info("=" * 70)
    logger.info("Mistral model: %s", MISTRAL_MODEL)
    logger.info("ASR model: %s", MODEL_NAME)
    logger.info("Sample rate: %s Hz", SAMPLE_RATE)
    logger.info("Speaker diarization: DISABLED")
    logger.info("WebSocket endpoint: /ws/meeting")
    logger.info("WebSocket diagnostic endpoint: /ws/test")
    logger.info("Summary endpoint: /api/meeting/summarize")
    logger.info("Frontend directory: %s", FRONTEND_DIR)
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("MeetMind backend shutting down.")