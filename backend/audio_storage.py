"""
MeetMind — preparing recordings for storage in the database.

Every recording (live or uploaded, meeting or consultation) is kept in
meetmind.db as a BLOB. Before it is stored it is re-encoded to a compact
mono MP3 with FFmpeg, which every browser's <audio> element can play and
seek. If FFmpeg is missing or the encode fails, the original file is
stored instead, so a recording is never lost because of compression.

Transcription never reads these copies: Parrotlet keeps working on its
own WAV (live) / normalized WAV (upload), exactly as before.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

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
