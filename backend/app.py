"""
MeetMind
FastAPI application.

Complete flow:

Browser
    ↓
/ws/meeting
    ↓
Complete recording
    ↓
Parrotlet-A 2.5 Pro
    ↓
Complete transcript
    ↓
Frontend displays transcript
    ↓
User clicks "Create Summary"
    ↓
/api/meeting/summarize
    ↓
Llama 3.1 8B / Ollama
    ↓
Meeting intelligence

Speaker diarization:
Disabled
"""

import json
from pathlib import Path
from typing import Any, List, Optional

from fastapi import (
    FastAPI,
    WebSocket,
    HTTPException,
    Request,
)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
import auth

from meeting_websocket import meeting_websocket

from meeting_intelligence import (
    generate_meeting_summary,
    LLAMA_MODEL,
)

from parrotlet_transcriber_gpu import (
    MODEL_NAME,
    SAMPLE_RATE,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

FRONTEND_DIR = BASE_DIR.parent / "frontend"

INDEX_FILE = FRONTEND_DIR / "index.html"

# Product-flow pages that wrap the (untouched) recorder app in index.html.
LANDING_FILE = FRONTEND_DIR / "landing.html"
AUTH_FILE = FRONTEND_DIR / "auth.html"      # one page, serves both /sign-in and /sign-up
ADMIN_FILE = FRONTEND_DIR / "admin.html"
ASSETS_DIR = FRONTEND_DIR / "assets"


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="MeetMind",
    description=(
        "AI Meeting Intelligence using "
        "Parrotlet-A 2.5 Pro and "
        "Llama 3.1 8B"
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
# STARTUP  (DB schema + seed admin account)
# ============================================================

@app.on_event("startup")
async def on_startup():
    db.init_db()
    db.ensure_seed_admin(auth.hash_password("admin123"))


# ============================================================
# AUTH ROUTER
# ============================================================

app.include_router(auth.router)


# ============================================================
# NO-STALE-CACHE MIDDLEWARE
# ============================================================
#
# Without this, a browser can serve a stale cached page/script after
# login state changes (e.g. after sign-in/sign-out), causing an
# infinite redirect loop between /sign-in and /app.

@app.middleware("http")
async def no_stale_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/") or not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ============================================================
# STATIC ASSETS  (shared CSS/JS for the product-flow pages)
# ============================================================

if ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=ASSETS_DIR),
        name="assets",
    )


# ============================================================
# REQUEST SCHEMA
# ============================================================

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


# ============================================================
# PAGE ROUTES
# ============================================================
#
# Routing / layout shell only. The recorder app itself (index.html)
# is served from "/app". Its WebSocket uses window.location.host
# (not a path) and its API calls use absolute paths, so the move is
# transparent to it.
#
# Server-side session/role gating (the no-stale-cache middleware above
# keeps a browser from replaying a cached page across a login-state
# change). frontend/assets/app-guard.js and auth-store.js layer
# client-side UX on top of this, but this is the real gate.

def _serve(page: Path) -> FileResponse:

    if not page.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frontend file not found: {page}",
        )

    return FileResponse(page, media_type="text/html")


@app.get("/")
async def home():
    # Landing page — first thing a visitor sees, pre-login.
    return _serve(LANDING_FILE)


@app.get("/app")
async def app_view(request: Request):
    # Post-login app view (the original single-page recorder UI).
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/sign-in?next=/app")
    if user["role"] == "admin":
        return RedirectResponse(url="/admin")
    return _serve(INDEX_FILE)


@app.get("/sign-in")
async def sign_in_view(request: Request):
    # Single auth page; the sign-in panel is shown by default.
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse(url=auth.landing_path_for_role(user["role"]))
    return _serve(AUTH_FILE)


@app.get("/sign-up")
async def sign_up_view(request: Request):
    # Same page; auth.html reads the path and opens the sign-up panel.
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse(url=auth.landing_path_for_role(user["role"]))
    return _serve(AUTH_FILE)


@app.get("/admin")
async def admin_view(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/sign-in?next=/admin")
    if user["role"] != "admin":
        return RedirectResponse(url="/app")
    return _serve(ADMIN_FILE)


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "MeetMind",
        "speech_model": MODEL_NAME,
        "llm_model": LLAMA_MODEL,
        "speaker_diarization": False,
    }


# ============================================================
# API INFORMATION
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
            "Llama 3.1 8B via Ollama",
            "Meeting intelligence",
        ],
        "speech_to_text": MODEL_NAME,
        "sample_rate": SAMPLE_RATE,
        "llm": LLAMA_MODEL,
        "speaker_diarization": False,
        "processing_mode": "record_then_process",
        "websocket": "/ws/meeting",
        "summary_endpoint": "/api/meeting/summarize",
    }


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/ws/meeting")
async def websocket_endpoint(
    websocket: WebSocket,
):
    await meeting_websocket(
        websocket
    )


# ============================================================
# MEETING HISTORY
# ============================================================

@app.get("/api/meetings")
async def api_list_meetings(
    request: Request,
    scope: str = "mine",
):
    user = auth.require_user(request)

    if scope == "all":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        rows = db.list_meetings()
    else:
        rows = db.list_meetings(user_id=user["id"])

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "createdAt": row["created_at"],
            "hasSummary": bool(row["has_summary"]),
            "transcriptChars": row["transcript_chars"],
            "username": row["username"],
            "email": row["email"],
        }
        for row in rows
    ]


@app.get("/api/meetings/{meeting_id}")
async def api_get_meeting(
    meeting_id: int,
    request: Request,
):
    user = auth.require_user(request)

    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    if meeting["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You don't have access to this meeting.")

    return {
        "id": meeting["id"],
        "title": meeting["title"],
        "createdAt": meeting["created_at"],
        "transcript": meeting["transcript"],
        "summary": json.loads(meeting["summary_json"]) if meeting["summary_json"] else None,
        "username": meeting["username"],
        "email": meeting["email"],
    }


@app.patch("/api/meetings/{meeting_id}")
async def api_update_meeting(
    meeting_id: int,
    request: MeetingUpdateRequest,
    http_request: Request,
):
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
        raise HTTPException(status_code=403, detail="You don't have access to this meeting.")

    updates = request.dict(exclude_unset=True)

    summary = json.loads(meeting["summary_json"]) if meeting["summary_json"] else {}
    summary.update(updates)

    fields = {"summary_json": json.dumps(summary)}
    if "title" in updates and updates["title"]:
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


# ============================================================
# CREATE SUMMARY
# ============================================================

@app.post("/api/meeting/summarize")
async def create_summary(
    request: SummaryRequest,
    http_request: Request,
):
    transcript = (
        request.transcript or ""
    ).strip()

    # --------------------------------------------------------
    # Validate transcript
    # --------------------------------------------------------

    if not transcript:
        return {
            "success": False,
            "error": "Transcript is empty.",
        }

    print()
    print("=" * 70)
    print("MEETMIND SUMMARY REQUEST")
    print("=" * 70)

    print(
        "Transcript length:",
        len(transcript),
        "characters",
    )

    print(
        "LLM:",
        LLAMA_MODEL,
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Generate summary
    # --------------------------------------------------------

    try:
        result = generate_meeting_summary(
            transcript
        )

    except Exception as exc:
        print()
        print(
            "Summary generation failed:"
        )

        print(
            repr(exc)
        )

        return {
            "success": False,
            "error": str(exc),
        }

    # --------------------------------------------------------
    # Return result
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
    }

    # --------------------------------------------------------
    # Save to history (best-effort — must never fail the request)
    # --------------------------------------------------------

    user = auth.get_current_user(http_request)
    if user:
        try:
            meeting = db.create_meeting(
                user_id=user["id"],
                title=payload["title"],
                transcript=transcript,
                summary_json=json.dumps(payload),
            )
            payload["meeting_id"] = meeting["id"]
        except Exception as exc:
            print()
            print("Saving meeting to history failed:")
            print(repr(exc))

    return payload
