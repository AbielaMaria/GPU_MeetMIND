"""
MeetNotes - Local Parrotlet GPU Transcriber

Parrotlet-A 2.5 Pro runs locally on the NVIDIA GPU.

Architecture:

    MeetNotes FastAPI
          |
          v
    Complete WAV recording
          |
          v
    30-second chunks
          |
          v
    Parrotlet-A 2.5 Pro
          |
          | NVIDIA CUDA GPU
          v
    Chunk transcripts
          |
          v
    Combined complete transcript

Optimizations:
    - Model loaded only once
    - CUDA inference mode
    - No unnecessary CUDA cache clearing after every chunk
    - Accurate CUDA timing
    - GPU memory monitoring
    - Real-Time Factor (RTF) measurement
    - Detailed preprocessing/inference timing
    - 30-second Parrotlet limit preserved

No Google Colab.
No ngrok.
No external ASR API.
"""

import gc
import time
import wave
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import torch
from transformers import AutoModel


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "ekacare/parrotlet-a-2.5-pro"

SAMPLE_RATE = 16000

# Parrotlet short-form inference limit.
# Keep this at 30 seconds.
CHUNK_SECONDS = 30

CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS


# ============================================================
# GPU CONFIGURATION
# ============================================================

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Use inference mode for PyTorch operations.
# This reduces autograd overhead during ASR inference.
INFERENCE_MODE = True


# ============================================================
# GLOBAL MODEL
# ============================================================

_model = None


# ============================================================
# GPU INFORMATION
# ============================================================

def print_gpu_information():
    """
    Print CUDA and GPU information.
    """

    print()
    print("=" * 70)
    print("MEETNOTES - GPU INFORMATION")
    print("=" * 70)

    print("PyTorch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    print("Selected device:", DEVICE)

    if not torch.cuda.is_available():

        print()
        print("WARNING: CUDA is NOT available.")
        print("Parrotlet will run on CPU.")
        print("=" * 70)

        return

    gpu_index = torch.cuda.current_device()

    gpu_name = torch.cuda.get_device_name(gpu_index)

    properties = torch.cuda.get_device_properties(gpu_index)

    total_memory = (
        properties.total_memory / (1024 ** 3)
    )

    allocated_memory = (
        torch.cuda.memory_allocated(gpu_index)
        / (1024 ** 3)
    )

    reserved_memory = (
        torch.cuda.memory_reserved(gpu_index)
        / (1024 ** 3)
    )

    free_memory = (
        total_memory - allocated_memory
    )

    print("GPU:", gpu_name)
    print("GPU index:", gpu_index)
    print("Total VRAM:", f"{total_memory:.2f} GB")
    print("Allocated VRAM:", f"{allocated_memory:.2f} GB")
    print("Reserved VRAM:", f"{reserved_memory:.2f} GB")
    print("Approx. free VRAM:", f"{free_memory:.2f} GB")

    print("=" * 70)


# ============================================================
# GPU MEMORY INFORMATION
# ============================================================

def print_gpu_memory(prefix="GPU"):
    """
    Print current PyTorch CUDA memory usage.
    """

    if not torch.cuda.is_available():
        return

    gpu_index = torch.cuda.current_device()

    allocated = (
        torch.cuda.memory_allocated(gpu_index)
        / (1024 ** 3)
    )

    reserved = (
        torch.cuda.memory_reserved(gpu_index)
        / (1024 ** 3)
    )

    print(
        f"{prefix} memory - "
        f"allocated: {allocated:.2f} GB | "
        f"reserved: {reserved:.2f} GB"
    )


# ============================================================
# LOAD MODEL
# ============================================================

def load_model():
    """
    Load Parrotlet-A 2.5 Pro once.

    The model remains loaded for subsequent recordings/chunks.
    """

    global _model

    if _model is not None:
        return _model

    print()
    print("=" * 70)
    print("MEETNOTES - LOADING PARROTLET")
    print("=" * 70)

    print("Model:", MODEL_NAME)
    print("Device:", DEVICE)

    if DEVICE == "cuda":

        print(
            "GPU:",
            torch.cuda.get_device_name(0),
        )

        print(
            "CUDA:",
            torch.version.cuda,
        )

    print("Loading model...")

    start_time = time.perf_counter()

    try:

        _model = AutoModel.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True,
            device_map="auto",
        )

    except Exception as exc:

        _model = None

        print()
        print("FAILED TO LOAD PARROTLET")
        print(repr(exc))

        raise RuntimeError(
            "Could not load Parrotlet-A 2.5 Pro. "
            "Check the GPU, PyTorch/CUDA installation, "
            "Hugging Face access, and model dependencies."
        ) from exc

    # --------------------------------------------------------
    # Put model in evaluation mode if supported.
    # --------------------------------------------------------

    try:

        if hasattr(_model, "eval"):
            _model.eval()

    except Exception as exc:

        print(
            "WARNING: Could not set model to eval mode:",
            repr(exc),
        )

    elapsed = (
        time.perf_counter()
        - start_time
    )

    print()
    print("Parrotlet loaded successfully.")
    print(
        "Load time:",
        f"{elapsed:.2f} seconds",
    )

    print_gpu_information()
    print_gpu_memory("After model loading")

    return _model


# ============================================================
# GPU SYNCHRONIZATION
# ============================================================

def synchronize_gpu():
    """
    Synchronize CUDA so timing measurements represent
    completed GPU work.
    """

    if torch.cuda.is_available():
        torch.cuda.synchronize()


# ============================================================
# GPU MEMORY CLEANUP
# ============================================================

def clear_gpu_memory():
    """
    Emergency GPU memory cleanup.

    IMPORTANT:
    This should NOT be called after every successful chunk.

    It is primarily intended for error/OOM recovery.
    """

    gc.collect()

    if torch.cuda.is_available():

        torch.cuda.empty_cache()

        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass


# ============================================================
# WAV INFORMATION
# ============================================================

def get_wav_duration(
    audio_path: Path,
) -> float:

    with wave.open(
        str(audio_path),
        "rb",
    ) as wav:

        frames = wav.getnframes()
        sample_rate = wav.getframerate()

    if sample_rate <= 0:

        raise ValueError(
            "Invalid WAV sample rate."
        )

    return frames / sample_rate


# ============================================================
# MODEL DEVICE CHECK
# ============================================================

def inspect_model_device(model: Any):
    """
    Try to determine where the Parrotlet model is located.

    Because device_map='auto' is used, the model may have
    multiple devices/components. Therefore this is only
    diagnostic information.
    """

    print()
    print("-" * 70)
    print("PARROTLET DEVICE CHECK")
    print("-" * 70)

    try:

        if hasattr(model, "hf_device_map"):

            print("Hugging Face device map:")

            print(model.hf_device_map)

        elif hasattr(model, "device"):

            print(
                "Model device:",
                model.device,
            )

        else:

            print(
                "Model device could not be determined automatically."
            )

    except Exception as exc:

        print(
            "Could not inspect model device:",
            repr(exc),
        )

    print("-" * 70)


# ============================================================
# TRANSCRIBE ONE CHUNK
# ============================================================

def transcribe_chunk(
    model: Any,
    audio: np.ndarray,
    chunk_number: int,
    total_chunks: int,
):
    """
    Transcribe one <=30-second audio chunk.

    The Parrotlet model API is kept unchanged:

        model.transcribe(audio, SAMPLE_RATE)
    """

    print()
    print("-" * 70)

    print(
        f"PARROTLET CHUNK "
        f"{chunk_number}/{total_chunks}"
    )

    duration = len(audio) / SAMPLE_RATE

    print(
        "Chunk duration:",
        f"{duration:.2f} seconds",
    )

    print(
        "Running inference on:",
        DEVICE,
    )

    # --------------------------------------------------------
    # GPU memory before inference
    # --------------------------------------------------------

    print_gpu_memory("Before inference")

    # --------------------------------------------------------
    # Synchronize before timing
    # --------------------------------------------------------

    synchronize_gpu()

    start_time = time.perf_counter()

    try:

        # ----------------------------------------------------
        # Disable autograd during inference.
        # ----------------------------------------------------

        if INFERENCE_MODE:

            with torch.inference_mode():

                result = model.transcribe(
                    audio,
                    SAMPLE_RATE,
                )

        else:

            result = model.transcribe(
                audio,
                SAMPLE_RATE,
            )

        # ----------------------------------------------------
        # Make sure GPU work is complete before timing.
        # ----------------------------------------------------

        synchronize_gpu()

    except torch.cuda.OutOfMemoryError as exc:

        print()
        print(
            "CUDA OUT OF MEMORY!"
        )

        clear_gpu_memory()

        raise RuntimeError(
            f"CUDA OUT OF MEMORY while processing "
            f"chunk {chunk_number}/{total_chunks}."
        ) from exc

    except Exception as exc:

        clear_gpu_memory()

        raise RuntimeError(
            f"Parrotlet failed on chunk "
            f"{chunk_number}/{total_chunks}: "
            f"{exc}"
        ) from exc

    elapsed = (
        time.perf_counter()
        - start_time
    )

    # --------------------------------------------------------
    # Normalize result
    # --------------------------------------------------------

    text = ""
    segments = []

    if isinstance(
        result,
        dict,
    ):

        text = (
            result.get(
                "text",
                "",
            )
            or ""
        )

        segments = (
            result.get(
                "segments",
                [],
            )
            or []
        )

    elif isinstance(
        result,
        str,
    ):

        text = result

    else:

        text = str(result)

    text = " ".join(
        text.split()
    ).strip()

    # --------------------------------------------------------
    # Real-Time Factor for this chunk
    # --------------------------------------------------------

    chunk_rtf = (
        elapsed / duration
        if duration > 0
        else 0.0
    )

    chunk_speed = (
        1.0 / chunk_rtf
        if chunk_rtf > 0
        else 0.0
    )

    print()
    print(
        "Inference time:",
        f"{elapsed:.2f} seconds",
    )

    print(
        "Chunk RTF:",
        f"{chunk_rtf:.3f}",
    )

    if chunk_speed > 0:

        print(
            "Chunk speed:",
            f"{chunk_speed:.2f}x real-time",
        )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    if text:

        print()
        print("TRANSCRIPT:")
        print(text)

    else:

        print(
            "[No speech detected]"
        )

    print_gpu_memory("After inference")

    print("-" * 70)

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT call clear_gpu_memory() here.
    #
    # The model stays loaded and PyTorch can reuse
    # allocated CUDA memory for the next chunk.
    # --------------------------------------------------------

    return {
        "text": text,
        "segments": segments,
        "inference_time": elapsed,
        "chunk_duration": duration,
        "rtf": chunk_rtf,
    }


# ============================================================
# TRANSCRIBE COMPLETE WAV
# ============================================================

def transcribe_audio(
    audio_path: str,
):
    """
    Transcribe a complete meeting recording.

    Recordings longer than 30 seconds are split into
    30-second chunks.

    Example:

        97 seconds

        -> 30 sec
        -> 30 sec
        -> 30 sec
        -> 7 sec

    The chunks are currently processed sequentially because
    the Parrotlet custom transcribe() API has not been assumed
    to support batched audio.
    """

    audio_path = Path(audio_path)

    # ========================================================
    # Validate file
    # ========================================================

    if not audio_path.exists():

        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    if not audio_path.is_file():

        raise ValueError(
            f"Audio path is not a file: {audio_path}"
        )

    if audio_path.stat().st_size == 0:

        raise ValueError(
            f"Audio file is empty: {audio_path}"
        )

    # ========================================================
    # Load model
    # ========================================================

    model = load_model()

    inspect_model_device(model)

    # ========================================================
    # Load audio
    # ========================================================

    print()
    print("=" * 70)
    print("MEETNOTES - LOCAL PARROTLET TRANSCRIPTION")
    print("=" * 70)

    print(
        "Audio file:",
        audio_path,
    )

    print(
        "Sample rate:",
        SAMPLE_RATE,
    )

    print(
        "Chunk size:",
        f"{CHUNK_SECONDS} seconds",
    )

    # --------------------------------------------------------
    # Measure audio loading separately.
    # --------------------------------------------------------

    audio_load_start = time.perf_counter()

    try:

        audio, sample_rate = librosa.load(
            str(audio_path),
            sr=SAMPLE_RATE,
            mono=True,
        )

    except Exception as exc:

        raise RuntimeError(
            f"Could not load audio file: "
            f"{audio_path}"
        ) from exc

    audio_load_time = (
        time.perf_counter()
        - audio_load_start
    )

    if audio is None:

        raise RuntimeError(
            "Audio loading returned None."
        )

    audio = np.asarray(
        audio,
        dtype=np.float32,
    )

    total_samples = len(audio)

    duration = (
        total_samples / SAMPLE_RATE
    )

    # ========================================================
    # Calculate chunks
    # ========================================================

    total_chunks = (
        total_samples
        + CHUNK_SAMPLES
        - 1
    ) // CHUNK_SAMPLES

    print(
        "Audio duration:",
        f"{duration:.2f} seconds",
    )

    print(
        "Total chunks:",
        total_chunks,
    )

    print(
        "Device:",
        DEVICE,
    )

    print(
        "Audio loading time:",
        f"{audio_load_time:.2f} seconds",
    )

    print("=" * 70)

    # ========================================================
    # Process chunks
    # ========================================================

    complete_transcript = []

    all_segments = []

    total_inference_time = 0.0

    overall_start = time.perf_counter()

    for chunk_index in range(total_chunks):

        start_sample = (
            chunk_index * CHUNK_SAMPLES
        )

        end_sample = min(
            start_sample + CHUNK_SAMPLES,
            total_samples,
        )

        chunk = audio[
            start_sample:end_sample
        ]

        start_second = (
            start_sample / SAMPLE_RATE
        )

        end_second = (
            end_sample / SAMPLE_RATE
        )

        print()
        print("=" * 70)

        print(
            f"PROCESSING CHUNK "
            f"{chunk_index + 1}/"
            f"{total_chunks}"
        )

        print(
            "Time range:",
            f"{start_second:.2f}s -> "
            f"{end_second:.2f}s",
        )

        print("=" * 70)

        result = transcribe_chunk(
            model=model,
            audio=chunk,
            chunk_number=chunk_index + 1,
            total_chunks=total_chunks,
        )

        text = result["text"]

        if text:

            complete_transcript.append(text)

        total_inference_time += (
            result["inference_time"]
        )

        # ----------------------------------------------------
        # Preserve segments if supplied.
        # ----------------------------------------------------

        segments = result.get(
            "segments",
            [],
        )

        if isinstance(
            segments,
            list,
        ):

            for segment in segments:

                if not isinstance(
                    segment,
                    dict,
                ):

                    continue

                segment_copy = dict(
                    segment
                )

                # --------------------------------------------
                # Adjust start timestamp
                # --------------------------------------------

                if "start" in segment_copy:

                    try:

                        segment_copy["start"] = (
                            float(
                                segment_copy["start"]
                            )
                            + start_second
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        pass

                # --------------------------------------------
                # Adjust end timestamp
                # --------------------------------------------

                if "end" in segment_copy:

                    try:

                        segment_copy["end"] = (
                            float(
                                segment_copy["end"]
                            )
                            + start_second
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        pass

                all_segments.append(
                    segment_copy
                )

    # ========================================================
    # Complete transcript
    # ========================================================

    transcript = " ".join(
        complete_transcript
    ).strip()

    total_processing_time = (
        time.perf_counter()
        - overall_start
    )

    # ========================================================
    # Performance metrics
    # ========================================================

    total_rtf = (
        total_processing_time / duration
        if duration > 0
        else 0.0
    )

    inference_rtf = (
        total_inference_time / duration
        if duration > 0
        else 0.0
    )

    processing_speed = (
        1.0 / total_rtf
        if total_rtf > 0
        else 0.0
    )

    inference_speed = (
        1.0 / inference_rtf
        if inference_rtf > 0
        else 0.0
    )

    non_inference_time = (
        total_processing_time
        - total_inference_time
    )

    # ========================================================
    # Final report
    # ========================================================

    print()
    print("=" * 70)
    print("PARROTLET TRANSCRIPTION COMPLETE")
    print("=" * 70)

    print(
        "Original duration:",
        f"{duration:.2f} seconds",
    )

    print(
        "Chunks processed:",
        total_chunks,
    )

    print()
    print(
        "Audio loading time:",
        f"{audio_load_time:.2f} seconds",
    )

    print(
        "Total inference time:",
        f"{total_inference_time:.2f} seconds",
    )

    print(
        "Non-inference processing time:",
        f"{non_inference_time:.2f} seconds",
    )

    print(
        "Total processing time:",
        f"{total_processing_time:.2f} seconds",
    )

    print()
    print(
        "Inference RTF:",
        f"{inference_rtf:.3f}",
    )

    if inference_speed > 0:

        print(
            "Inference speed:",
            f"{inference_speed:.2f}x real-time",
        )

    print(
        "Overall RTF:",
        f"{total_rtf:.3f}",
    )

    if processing_speed > 0:

        print(
            "Overall processing speed:",
            f"{processing_speed:.2f}x real-time",
        )

    print()
    print(
        "Device:",
        DEVICE,
    )

    if torch.cuda.is_available():

        print(
            "GPU:",
            torch.cuda.get_device_name(0),
        )

        print_gpu_memory(
            "Final"
        )

    print()
    print(
        "COMPLETE TRANSCRIPT:"
    )

    print(
        transcript
    )

    print("=" * 70)

    return {
        "text": transcript,

        "segments": all_segments,

        "duration": duration,

        "model": MODEL_NAME,

        "chunks_processed": total_chunks,

        "inference_time": total_inference_time,

        "processing_time": total_processing_time,

        "audio_loading_time": audio_load_time,

        "non_inference_time": non_inference_time,

        "inference_rtf": inference_rtf,

        "rtf": total_rtf,

        "inference_speed": inference_speed,

        "processing_speed": processing_speed,

        "device": DEVICE,
    }


# ============================================================
# OPTIONAL COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    import sys

    print()
    print("=" * 70)
    print("MEETNOTES - LOCAL PARROTLET TEST")
    print("=" * 70)

    print_gpu_information()

    if len(sys.argv) < 2:

        print()
        print("Usage:")

        print(
            "python parrotlet_transcriber_gpu.py "
            "/path/to/audio.wav"
        )

        raise SystemExit(1)

    audio_file = sys.argv[1]

    result = transcribe_audio(
        audio_file
    )

    print()
    print("=" * 70)
    print("FINAL TRANSCRIPT")
    print("=" * 70)

    print(
        result["text"]
    )

    print("=" * 70)

    print()
    print("PERFORMANCE")
    print("=" * 70)

    print(
        "Audio duration:",
        f"{result['duration']:.2f}s",
    )

    print(
        "Processing time:",
        f"{result['processing_time']:.2f}s",
    )

    print(
        "Inference time:",
        f"{result['inference_time']:.2f}s",
    )

    print(
        "RTF:",
        f"{result['rtf']:.3f}",
    )

    if result["processing_speed"] > 0:

        print(
            "Speed:",
            f"{result['processing_speed']:.2f}x real-time",
        )

    print("=" * 70)