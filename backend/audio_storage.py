"""
MeetMind — preparing recordings for storage in the database.

Every recording (live or uploaded, meeting or consultation) is kept in
meetmind.db as a BLOB. Before it is stored it is re-encoded to a compact
mono MP3 with FFmpeg, which every browser's <audio> element can play and
seek. If FFmpeg is missing or the encode fails, the original file is
stored instead, so a recording is never lost because of compression.

Transcription never reads these copies: Parrotlet keeps working on its
own WAV (live) / normalized WAV (upload), exactly as before.

It also serves them back (audio_fields / audio_response), for every
template's history: meetings and consultations from app.py, interviews
from interview_routes.py.
"""

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

import database as db

logger = logging.getLogger("meetmind.audio")

MP3_BITRATE = "64k"

# Browser-playable MIME type per stored file extension.
MIME_BY_EXT = {
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "webm": "audio/webm",
}


def _encode_mp3(source: Path) -> bytes:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is not installed or is not available in PATH.")

    with tempfile.TemporaryDirectory(prefix="meetmind_mp3_") as tmp:
        target = Path(tmp) / "recording.mp3"
        result = subprocess.run(
            [
                ffmpeg_path,
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(source),
                "-map", "0:a:0",
                "-vn",
                "-ac", "1",
                "-c:a", "libmp3lame",
                "-b:a", MP3_BITRATE,
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip()[-800:] or "Unknown FFmpeg error")
        data = target.read_bytes() if target.exists() else b""
        if not data:
            raise RuntimeError("FFmpeg produced an empty MP3.")
        return data


def prepare_for_storage(source: Path) -> tuple:
    """
    (bytes, mime_type, file_ext) to store for the recording at `source`:
    an MP3 when FFmpeg can make one, otherwise the original file as-is.
    """
    source = Path(source)
    try:
        data = _encode_mp3(source)
        logger.info(
            "Recording encoded to MP3 for storage: %s (%d -> %d bytes)",
            source.name,
            source.stat().st_size,
            len(data),
        )
        return data, MIME_BY_EXT["mp3"], "mp3"
    except Exception as exc:
        ext = source.suffix.lower().lstrip(".") or "wav"
        logger.warning(
            "MP3 encode failed for %s (%s); storing the original %s instead.",
            source.name,
            exc,
            ext.upper(),
        )
        return source.read_bytes(), MIME_BY_EXT.get(ext, "application/octet-stream"), ext


# ============================================================
# PLAYBACK (meeting_audio / doctor_audio / interview_audio)
# ============================================================

_RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")


def audio_fields(table: str, parent_id: int, url: str) -> dict:
    """`hasAudio` / `audio` for a meeting, consultation or interview payload."""
    meta = db.get_audio_meta(table, parent_id)
    if not meta:
        return {"hasAudio": False, "audio": None}
    return {
        "hasAudio": True,
        "audio": {
            "url": url,
            "mimeType": meta["mime_type"],
            "sizeBytes": meta["size_bytes"],
            "source": meta["source"],
            "originalFilename": meta["original_filename"],
        },
    }


def audio_response(request: Request, table: str, parent_id: int, filename_stem: str):
    """
    Stream a stored recording, honouring a single HTTP Range request so the
    audio player can seek (and the browser can read the duration) without
    downloading the whole file first.
    """
    meta = db.get_audio_meta(table, parent_id)
    if not meta:
        raise HTTPException(status_code=404, detail="No recording is stored for this item.")

    size = meta["size_bytes"]
    start, end = 0, size - 1
    status_code = 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename_stem}.{meta["file_ext"]}"',
        "Cache-Control": "private, max-age=3600",
    }

    range_header = (request.headers.get("range") or "").strip()
    if range_header:
        match = _RANGE_PATTERN.fullmatch(range_header)
        valid = bool(match and (match.group(1) or match.group(2)))
        if valid:
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            end = min(end, size - 1)
        if not valid or start >= size or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        db.iter_audio(table, parent_id, start, end),
        status_code=status_code,
        media_type=meta["mime_type"],
        headers=headers,
    )
