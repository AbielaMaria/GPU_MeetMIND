"""
MeetMind FastAPI application.

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

from fastapi import (
    FastAPI,
    WebSocket,
    HTTPException,
    Request,
)

from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from fastapi.responses import (
    FileResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from meeting_websocket import (
    meeting_websocket,
)

from meeting_intelligence import (
    generate_meeting_summary,
    LLAMA_MODEL,
)

from parrotlet_transcriber import (
    MODEL_NAME,
    SAMPLE_RATE,
)

import database as db
import auth


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"

# Product-flow pages that wrap the (untouched) app in index.html.
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
# DATABASE + AUTH
# ============================================================

@app.on_event("startup")
def _init_auth():
    db.init_db()
    # Bootstraps a single admin account only if the DB has no users yet
    # (fresh install). Existing databases / accounts are left untouched.
    db.ensure_seed_admin(auth.hash_password("admin123"))


app.include_router(auth.router)


# ============================================================
# REQUEST SCHEMA
# ============================================================

class SummaryRequest(BaseModel):

    transcript: str


# ============================================================
# STATIC ASSETS  (shared CSS/JS for the new product-flow pages)
# ============================================================

if ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=ASSETS_DIR),
        name="assets",
    )


# Never let a browser serve a stale page or script out of its cache.
#
# This covers the HTML pages too, not just /assets/*. Page routes had no
# cache headers at all, so browsers applied heuristic freshness and served
# /app, /sign-in and /admin straight from cache — which meant an old cached
# copy of app-guard.js kept running (redirecting to /sign-in based on the
# long-gone localStorage session) while the server said the user was signed
# in, bouncing the browser between the two forever.
#
# The app is served by the same process that serves the API, so the cost of
# revalidating is negligible; correctness matters far more here.
@app.middleware("http")
async def _no_stale_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/") or not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ============================================================
# PAGE ROUTES
# ============================================================
#
# Routing / layout shell only. The app itself (index.html) is
# unchanged — it just moved from "/" to "/app". Its WebSocket
# uses window.location.host (not a path) and its API calls use
# absolute paths, so the move is transparent to it.
#
# Server-side session/role check now guards /app and /admin (see
# auth.get_current_user, backed by database.py's sessions table).
# Client-side checks in app-guard.js / admin.html remain only as a
# defense-in-depth fallback (e.g. the browser back/forward cache).

def _serve(page: Path) -> FileResponse:

    if not page.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frontend file not found: {page}"
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
    # The recorder is a user-facing feature; an admin account is for
    # managing users and reviewing their meetings only.
    if user["role"] == "admin":
        return RedirectResponse(url="/admin")
    return _serve(INDEX_FILE)


def _redirect_if_already_signed_in(request: Request):
    """
    An already-authenticated visitor hitting /sign-in or /sign-up should
    bounce to their app straight away. This used to be done client-side
    (auth-forms.js calling /api/auth/session after the page loaded), which
    works but leaves a brief window where the sign-in form is visible
    before the async check resolves -- reload during that window and it
    looks like the page is stuck re-showing the sign-in form forever.
    Deciding it here, before the page is even served, removes that window.
    """
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse(url=auth.landing_path_for_role(user["role"]))
    return None


@app.get("/sign-in")
async def sign_in_view(request: Request):
    # Single auth page; the sign-in panel is shown by default.
    return _redirect_if_already_signed_in(request) or _serve(AUTH_FILE)


@app.get("/sign-up")
async def sign_up_view(request: Request):
    # Same page; auth.html reads the path and opens the sign-up panel.
    return _redirect_if_already_signed_in(request) or _serve(AUTH_FILE)


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

        "status":
            "healthy",

        "service":
            "MeetMind",

        "speech_model":
            MODEL_NAME,

        "llm_model":
            LLAMA_MODEL,

        "speaker_diarization":
            False,
    }


# ============================================================
# API INFORMATION
# ============================================================

@app.get("/api/info")
async def api_info():

    return {

        "project":
            "MeetMind",

        "version":
            "3.0.0",

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

        "speech_to_text":
            MODEL_NAME,

        "sample_rate":
            SAMPLE_RATE,

        "llm":
            LLAMA_MODEL,

        "speaker_diarization":
            False,

        "processing_mode":
            "record_then_process",

        "websocket":
            "/ws/meeting",

        "summary_endpoint":
            "/api/meeting/summarize",
    }


# ============================================================
# MEETING HISTORY
# ============================================================
#
# A user sees their own meetings; an admin sees everyone's. Both use the
# same two endpoints -- the scope is decided here from the session's role,
# never from anything the client sends.

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

    # "all" is an admin-only view of every user's meetings.
    if scope == "all":
        if user["role"] != "admin":
            raise HTTPException(
                status_code=403,
                detail="Admin access required.",
            )
        rows = db.list_meetings()

    else:
        rows = db.list_meetings(user_id=user["id"])

    return [_meeting_row(r) for r in rows]


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: int, request: Request):

    user = auth.require_user(request)
    meeting = db.get_meeting(meeting_id)

    if not meeting:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found.",
        )

    # Owner or admin only.
    if meeting["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="You don't have access to that meeting.",
        )

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


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket(
    "/ws/meeting"
)
async def websocket_endpoint(
    websocket: WebSocket,
):

    await meeting_websocket(
        websocket
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
        request.transcript
        or ""
    ).strip()

    # --------------------------------------------------------
    # Validate transcript
    # --------------------------------------------------------

    if not transcript:

        return {

            "success":
                False,

            "error":
                "Transcript is empty.",

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

        result = (
            generate_meeting_summary(
                transcript
            )
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

            "success":
                False,

            "error":
                str(exc),
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
    # Save it to the signed-in user's history
    # --------------------------------------------------------
    # Done here rather than in the recorder so the frontend needs no extra
    # call: this endpoint is the one point where the transcript and its
    # summary exist together. A failure to save must never cost the user the
    # summary they just waited for, so it is best-effort.

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
            print("Could not save meeting to history:", repr(exc))

    return payload