"""
MeetMind - Record-then-process WebSocket

Flow:

    Browser microphone
        ↓
    PCM16 mono 16 kHz
        ↓
    FastAPI WebSocket
        ↓
    Complete WAV recording
        ↓
    Parrotlet-A 2.5 Pro
        ↓
    Complete transcript
        ↓
    Frontend displays transcript
        ↓
    User clicks "Create Summary"
        ↓
    POST /api/meeting/summarize
        ↓
    Llama 3.1 8B
        ↓
    Meeting intelligence

Speaker diarization:
    DISABLED

Maximum recording duration:
    10 minutes

The WebSocket does NOT automatically generate the summary.
"""

import asyncio
import json
import uuid
import wave

from pathlib import Path

from fastapi import (
    WebSocket,
    WebSocketDisconnect,
)

from parrotlet_transcriber_gpu import (
    MODEL_NAME,
    SAMPLE_RATE,
    transcribe_audio,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

RECORDINGS_DIR = BASE_DIR / "recordings"

RECORDINGS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# AUDIO CONFIGURATION
# ============================================================

CHANNELS = 1

# PCM16 = 2 bytes/sample
SAMPLE_WIDTH = 2

# Maximum recording duration = 10 minutes
MAX_RECORDING_SECONDS = 600

MAX_AUDIO_BYTES = (
    SAMPLE_RATE
    * CHANNELS
    * SAMPLE_WIDTH
    * MAX_RECORDING_SECONDS
)


# ============================================================
# SEND JSON
# ============================================================

async def send_message(
    websocket: WebSocket,
    payload: dict,
):
    await websocket.send_text(
        json.dumps(
            payload,
            ensure_ascii=False,
        )
    )


# ============================================================
# SAVE WAV
# ============================================================

def save_wav(
    audio_data: bytes,
    output_path: Path,
):
    with wave.open(
        str(output_path),
        "wb",
    ) as wav:

        wav.setnchannels(
            CHANNELS
        )

        wav.setsampwidth(
            SAMPLE_WIDTH
        )

        wav.setframerate(
            SAMPLE_RATE
        )

        wav.writeframes(
            audio_data
        )


# ============================================================
# WEBSOCKET
# ============================================================

async def meeting_websocket(
    websocket: WebSocket,
):

    await websocket.accept()

    # --------------------------------------------------------
    # SESSION STATE
    # --------------------------------------------------------

    meeting_id = str(
        uuid.uuid4()
    )

    audio_buffer = bytearray()

    recording = False

    processing = False

    transcript_available = False

    current_transcript = ""

    current_audio_path = None

    current_duration = 0.0

    print()
    print("=" * 70)
    print("MEETMIND - MEETING WEBSOCKET")
    print("=" * 70)

    print(
        "Meeting ID:",
        meeting_id,
    )

    print(
        "ASR:",
        MODEL_NAME,
    )

    print(
        "Audio:",
        f"PCM16 mono {SAMPLE_RATE} Hz",
    )

    print(
        "Maximum recording:",
        f"{MAX_RECORDING_SECONDS} seconds",
    )

    print(
        "Speaker diarization: DISABLED"
    )

    print("=" * 70)

    try:

        # ====================================================
        # CONNECTION CONFIRMATION
        # ====================================================

        await send_message(
            websocket,
            {
                "type": "connected",

                "meeting_id":
                    meeting_id,

                "speech_model":
                    MODEL_NAME,

                "sample_rate":
                    SAMPLE_RATE,

                "speaker_diarization":
                    False,

                "max_recording_seconds":
                    MAX_RECORDING_SECONDS,
            },
        )

        # ====================================================
        # MAIN LOOP
        # ====================================================

        while True:

            message = await websocket.receive()

            # =================================================
            # BROWSER DISCONNECTED
            # =================================================

            if (
                message.get("type")
                == "websocket.disconnect"
            ):

                break

            # =================================================
            # BINARY AUDIO
            # =================================================

            audio_bytes = message.get("bytes")

            if audio_bytes is not None:

                if recording and not processing:

                    # -----------------------------------------
                    # Prevent recording beyond 10 minutes
                    # -----------------------------------------

                    if (
                        len(audio_buffer)
                        + len(audio_bytes)
                        > MAX_AUDIO_BYTES
                    ):

                        recording = False

                        print()
                        print("=" * 70)
                        print("MAXIMUM RECORDING DURATION REACHED")
                        print("=" * 70)

                        await send_message(
                            websocket,
                            {
                                "type":
                                    "recording_limit_reached",

                                "message":
                                    "Maximum recording duration of 10 minutes reached. Processing recording.",

                                "max_recording_seconds":
                                    MAX_RECORDING_SECONDS,
                            },
                        )

                        # Process the audio exactly like stop.
                        if audio_buffer:
                            processing = True

                            audio_path = (
                                RECORDINGS_DIR
                                / f"{meeting_id}.wav"
                            )

                            save_wav(
                                bytes(audio_buffer),
                                audio_path,
                            )

                            current_audio_path = audio_path

                            current_duration = (
                                len(audio_buffer)
                                /
                                (
                                    SAMPLE_RATE
                                    * SAMPLE_WIDTH
                                )
                            )

                            await process_recording(
                                websocket=websocket,
                                meeting_id=meeting_id,
                                audio_path=audio_path,
                                current_duration=current_duration,
                            )

                            processing = False
                            audio_buffer.clear()

                        continue

                    audio_buffer.extend(
                        audio_bytes
                    )

                continue

            # =================================================
            # TEXT COMMAND
            # =================================================

            text_message = message.get("text")

            if text_message is None:
                continue

            try:

                command = json.loads(
                    text_message
                )

            except json.JSONDecodeError:

                await send_message(
                    websocket,
                    {
                        "type":
                            "error",

                        "stage":
                            "control",

                        "message":
                            "Invalid JSON control message.",
                    },
                )

                continue

            command_type = command.get(
                "command"
            )

            # =================================================
            # START RECORDING
            # =================================================

            if command_type == "start":

                if recording:

                    await send_message(
                        websocket,
                        {
                            "type":
                                "error",

                            "stage":
                                "recording",

                            "message":
                                "Recording is already active.",
                        },
                    )

                    continue

                if processing:

                    await send_message(
                        websocket,
                        {
                            "type":
                                "error",

                            "stage":
                                "processing",

                            "message":
                                "Previous recording is still being processed.",
                        },
                    )

                    continue

                # ------------------------------------------------
                # NEW RECORDING
                # ------------------------------------------------

                meeting_id = str(
                    uuid.uuid4()
                )

                audio_buffer.clear()

                current_transcript = ""

                current_audio_path = None

                current_duration = 0.0

                transcript_available = False

                recording = True

                processing = False

                print()
                print("=" * 70)
                print("RECORDING STARTED")
                print("=" * 70)

                print(
                    "Meeting ID:",
                    meeting_id,
                )

                await send_message(
                    websocket,
                    {
                        "type":
                            "recording_started",

                        "meeting_id":
                            meeting_id,

                        "max_recording_seconds":
                            MAX_RECORDING_SECONDS,

                        "speaker_diarization":
                            False,
                    },
                )

                continue

            # =================================================
            # STOP RECORDING
            # =================================================

            if command_type == "stop":

                if not recording:

                    await send_message(
                        websocket,
                        {
                            "type":
                                "error",

                            "stage":
                                "recording",

                            "message":
                                "No active recording.",
                        },
                    )

                    continue

                # ------------------------------------------------
                # IMPORTANT:
                #
                # Stop accepting new audio immediately.
                # The existing audio_buffer remains intact.
                # ------------------------------------------------

                recording = False

                processing = True

                print()
                print("=" * 70)
                print("RECORDING STOPPED")
                print("=" * 70)

                print(
                    "Received audio bytes:",
                    len(audio_buffer),
                )

                # ------------------------------------------------
                # Tell frontend that STOP was received
                # ------------------------------------------------

                await send_message(
                    websocket,
                    {
                        "type":
                            "recording_stopped",

                        "meeting_id":
                            meeting_id,

                        "message":
                            "Recording stopped. Finalizing audio...",
                    },
                )

                # ------------------------------------------------
                # NO AUDIO
                # ------------------------------------------------

                if not audio_buffer:

                    processing = False

                    await send_message(
                        websocket,
                        {
                            "type":
                                "error",

                            "stage":
                                "recording",

                            "message":
                                "No audio was recorded.",
                        },
                    )

                    continue

                # ------------------------------------------------
                # SAVE WAV
                # ------------------------------------------------

                audio_path = (
                    RECORDINGS_DIR
                    / f"{meeting_id}.wav"
                )

                save_wav(
                    bytes(audio_buffer),
                    audio_path,
                )

                current_audio_path = (
                    audio_path
                )

                current_duration = (
                    len(audio_buffer)
                    /
                    (
                        SAMPLE_RATE
                        * SAMPLE_WIDTH
                    )
                )

                print(
                    "Saved recording:",
                    audio_path,
                )

                print(
                    "Duration:",
                    round(
                        current_duration,
                        2,
                    ),
                    "seconds",
                )

                # ------------------------------------------------
                # PROCESS WITH PARROTLET
                # ------------------------------------------------

                await process_recording(
                    websocket=websocket,
                    meeting_id=meeting_id,
                    audio_path=audio_path,
                    current_duration=current_duration,
                )

                processing = False

                # ------------------------------------------------
                # CLEAR BUFFER AFTER PROCESSING
                # ------------------------------------------------

                audio_buffer.clear()

                continue

            # =================================================
            # PING
            # =================================================

            if command_type == "ping":

                await send_message(
                    websocket,
                    {
                        "type":
                            "pong",
                    },
                )

                continue

            # =================================================
            # UNKNOWN COMMAND
            # =================================================

            await send_message(
                websocket,
                {
                    "type":
                        "error",

                    "stage":
                        "control",

                    "message":
                        f"Unknown command: {command_type}",
                },
            )

    except WebSocketDisconnect:

        print(
            "MeetMind browser disconnected."
        )

    except Exception as exc:

        print()
        print("=" * 70)
        print("MEETMIND WEBSOCKET ERROR")
        print("=" * 70)

        print(
            repr(exc)
        )

        print("=" * 70)

        try:

            await send_message(
                websocket,
                {
                    "type":
                        "error",

                    "stage":
                        "websocket",

                    "message":
                        str(exc),
                },
            )

        except Exception:
            pass


# ============================================================
# PROCESS RECORDING
# ============================================================

async def process_recording(
    websocket: WebSocket,
    meeting_id: str,
    audio_path: Path,
    current_duration: float,
):

    print()
    print("=" * 70)
    print("PROCESSING RECORDING")
    print("=" * 70)

    print(
        "Audio:",
        audio_path,
    )

    print(
        "Duration:",
        round(
            current_duration,
            2,
        ),
        "seconds",
    )

    # --------------------------------------------------------
    # TELL FRONTEND TRANSCRIPTION STARTED
    # --------------------------------------------------------

    await send_message(
        websocket,
        {
            "type":
                "processing_started",

            "stage":
                "transcription",

            "meeting_id":
                meeting_id,

            "message":
                "Recording complete. Transcribing with Parrotlet...",
        },
    )

    # --------------------------------------------------------
    # PARROTLET
    # --------------------------------------------------------

    try:

        transcription = (
            await asyncio.to_thread(
                transcribe_audio,
                str(audio_path),
            )
        )

    except Exception as exc:

        print()
        print("=" * 70)
        print("PARROTLET TRANSCRIPTION ERROR")
        print("=" * 70)

        print(
            repr(exc)
        )

        print("=" * 70)

        await send_message(
            websocket,
            {
                "type":
                    "error",

                "stage":
                    "transcription",

                "meeting_id":
                    meeting_id,

                "message":
                    str(exc),
            },
        )

        return

    # --------------------------------------------------------
    # GET TRANSCRIPT
    # --------------------------------------------------------

    transcript_text = (
        transcription.get(
            "text",
            "",
        )
        or ""
    ).strip()

    print()
    print("=" * 70)
    print("PARROTLET TRANSCRIPTION COMPLETE")
    print("=" * 70)

    print(
        transcript_text
    )

    print("=" * 70)

    # --------------------------------------------------------
    # SEND FINAL TRANSCRIPT
    # --------------------------------------------------------

    await send_message(
        websocket,
        {
            "type":
                "final_transcript",

            "meeting_id":
                meeting_id,

            "transcript":
                transcript_text,

            "segments":
                transcription.get(
                    "segments",
                    [],
                ),

            "duration":
                transcription.get(
                    "duration",
                    current_duration,
                ),

            "speech_model":
                MODEL_NAME,

            "speaker_diarization":
                False,

            "final":
                True,
        },
    )

    # --------------------------------------------------------
    # TRANSCRIPT READY
    # --------------------------------------------------------

    await send_message(
        websocket,
        {
            "type":
                "transcript_ready",

            "meeting_id":
                meeting_id,

            "message":
                (
                    "Transcript complete. "
                    "You can now create the meeting summary."
                    if transcript_text
                    else
                    "Transcription completed, but no text was detected."
                ),

            "can_create_summary":
                bool(transcript_text),
        },
    )

    print()
    print("=" * 70)
    print("TRANSCRIPT READY")
    print("=" * 70)

    print(
        transcript_text
    )

    print("=" * 70)