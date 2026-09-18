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

from pathlib import Path

from fastapi import (
    FastAPI,
    WebSocket,
    HTTPException,
)
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


# ============================================================
# PAGE ROUTES
# ============================================================
#
# Routing / layout shell only. The recorder app itself (index.html)
# is served from "/app". Its WebSocket uses window.location.host
# (not a path) and its API calls use absolute paths, so the move is
# transparent to it.
#
# Auth is enforced client-side for now (see frontend/assets/
# app-guard.js and auth-store.js). TODO(backend): add a real
# server-side session/role check here before returning
# INDEX_FILE / ADMIN_FILE.

def _serve(page: Path) -> FileResponse:

    if not page.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frontend file not found: {page}",
        )

    # no-store: these pages are actively changing during development, and a
    # browser that caches the HTML document itself (as opposed to the
    # versioned CSS/JS it links to) will keep rendering a stale DOM on a
    # given route no matter how thoroughly the user clears the cache for
    # other routes/tabs.
    return FileResponse(
        page,
        media_type="text/html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/")
async def home():
    # Landing page — first thing a visitor sees, pre-login.
    return _serve(LANDING_FILE)


@app.get("/app")
async def app_view():
    # Post-login app view (the original single-page recorder UI).
    return _serve(INDEX_FILE)


@app.get("/sign-in")
async def sign_in_view():
    # Single auth page; the sign-in panel is shown by default.
    return _serve(AUTH_FILE)


@app.get("/sign-up")
async def sign_up_view():
    # Same page; auth.html reads the path and opens the sign-up panel.
    return _serve(AUTH_FILE)


@app.get("/admin")
async def admin_view():
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
# CREATE SUMMARY
# ============================================================

@app.post("/api/meeting/summarize")
async def create_summary(
    request: SummaryRequest,
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

    return {
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
