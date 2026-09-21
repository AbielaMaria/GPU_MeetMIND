"""
MeetNotes - FastAPI Backend

Architecture:

    Browser
        |
        v
    /ws/meeting
        |
        v
    meeting_websocket.py
        |
        v
    Complete WAV recording
        |
        v
    Parrotlet-A 2.5 Pro
        |
        v
    Complete transcript
        |
        v
    Frontend
        |
        v
    POST /api/meeting/summarize
        |
        v
    meeting_intelligence.py
        |
        v
    mistral_client.py
        |
        v
    Mistral 128B API
        |
        v
    Structured Meeting Intelligence
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("meetnotes")


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = BASE_DIR.parent

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Product-flow pages that wrap the (untouched) recorder app in index.html.
INDEX_FILE = FRONTEND_DIR / "index.html"
LANDING_FILE = FRONTEND_DIR / "landing.html"
AUTH_FILE = FRONTEND_DIR / "auth.html"      # one page, serves both /sign-in and /sign-up
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
    title="MeetNotes API",
    description=(
        "MeetNotes meeting transcription and "
        "AI-powered meeting intelligence"
    ),
    version="1.0.0",
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
# REQUEST MODEL
# ============================================================

class SummaryRequest(BaseModel):
    transcript: str


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
            detail=f"Frontend file not found: {page}"
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
# APP  (post-login recorder UI)
# ============================================================

@app.get("/app")
async def root():
    """
    Serve the MeetNotes frontend.
    """

    index_file = FRONTEND_DIR / "index.html"

    if index_file.exists():

        return FileResponse(
            index_file
        )

    return JSONResponse(
        {
            "name": "MeetNotes",
            "status": "running",
            "message": (
                "Frontend index.html was not found."
            ),
        }
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    """
    Backend health check.
    """

    return {
        "status": "healthy",
        "service": "MeetNotes backend",

        "llm": MISTRAL_MODEL,

        "asr_model": MODEL_NAME,

        "sample_rate": SAMPLE_RATE,

        "speaker_diarization": False,
    }


# ============================================================
# API INFORMATION
# ============================================================

@app.get("/api/info")
async def api_info():
    """
    Return backend configuration information.
    """

    return {
        "name": "MeetNotes",

        "status": "running",

        "llm": {
            "provider": "Mistral API",
            "model": MISTRAL_MODEL,
        },

        "asr": {
            "model": MODEL_NAME,
            "sample_rate": SAMPLE_RATE,
        },

        "speaker_diarization": False,

        "endpoints": {
            "health": "/health",
            "info": "/api/info",
            "summarize": "/api/meeting/summarize",
            "meeting_websocket": "/ws/meeting",
        },
    }


# ============================================================
# MEETING WEBSOCKET
# ============================================================

@app.websocket("/ws/meeting")
async def websocket_endpoint(websocket):
    """
    Existing MeetNotes recording/transcription WebSocket.

    IMPORTANT:
    meeting_websocket.py defines a normal WebSocket handler,
    not a FastAPI APIRouter.

    Therefore we call the existing handler directly.
    """

    await meeting_websocket(websocket)


# ============================================================
# WEBSOCKET DIAGNOSTIC TEST
# ============================================================
#
# Temporary diagnostic endpoint used to determine whether the
# FastAPI/Starlette/Uvicorn WebSocket stack accepts connections
# independently of the MeetNotes meeting handler.
#
# Test with:
# python -c "import websocket; ws=websocket.create_connection('ws://10.184.36.80:8000/ws/test', timeout=10); print(ws.recv()); ws.close()"
#
@app.websocket("/ws/test")
async def websocket_test(websocket):
    print(">>> TEST WEBSOCKET HANDLER REACHED", flush=True)

    await websocket.accept()

    print(">>> TEST WEBSOCKET ACCEPTED", flush=True)

    await websocket.send_text("TEST_OK")

    await websocket.close()


# ============================================================
# MEETING SUMMARIZATION
# ============================================================

@app.post("/api/meeting/summarize")
async def summarize_meeting(
    request: SummaryRequest,
):
    """
    Generate structured meeting intelligence.

    Flow:

        Frontend
            |
            v
        /api/meeting/summarize
            |
            v
        generate_meeting_summary()
            |
            v
        Mistral 128B
            |
            v
        Structured meeting intelligence
    """

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

    # --------------------------------------------------------
    # EMPTY TRANSCRIPT
    # --------------------------------------------------------

    if not transcript:

        raise HTTPException(
            status_code=400,
            detail="Transcript cannot be empty.",
        )

    # --------------------------------------------------------
    # GENERATE SUMMARY
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # RETURN RESULT
        # ----------------------------------------------------

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

            "timeline": result.get(
                "timeline",
                [],
            ),
        }

    except HTTPException:

        raise

    except Exception as exc:

        logger.exception(
            "Meeting summarization failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Meeting summarization failed: "
                f"{exc}"
            ),
        ) from exc


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():

    logger.info("")
    logger.info("=" * 70)
    logger.info("MEETNOTES BACKEND STARTED")
    logger.info("=" * 70)

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
        "Frontend directory: %s",
        FRONTEND_DIR,
    )

    logger.info("=" * 70)
    logger.info("")


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event("shutdown")
async def shutdown_event():

    logger.info(
        "MeetNotes backend shutting down."
    )