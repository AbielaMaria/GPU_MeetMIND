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


from pathlib import Path

from fastapi import (
    FastAPI,
    WebSocket,
    HTTPException
)

from fastapi.responses import FileResponse
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from fastapi.responses import (
    FileResponse,
)
from pydantic import BaseModel

from meeting_websocket import (
    meeting_websocket,
)

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
# REQUEST SCHEMA
# ============================================================

class SummaryRequest(BaseModel):

    transcript: str


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    if not INDEX_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frontend not found: {INDEX_FILE}"
        )

    return FileResponse(
        INDEX_FILE,
        media_type="text/html"
    )


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