import os
import time
import numpy as np
import librosa
import torch

from transformers import AutoModel


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "ekacare/parrotlet-a-2.5-pro"

AUDIO_PATH = (
    "/home/boss/MeetNotes/GPU_MeetMIND/backend/"
    "Recording 4.wav"
)

SAMPLE_RATE = 16000


# ============================================================
# CHECK AUDIO FILE
# ============================================================

print("=" * 70)
print("PARROTLET - RECORDING 4 TEST")
print("=" * 70)

print(f"\nAudio file:")
print(AUDIO_PATH)

if not os.path.exists(AUDIO_PATH):
    print("\nERROR: Audio file not found!")
    print(AUDIO_PATH)
    raise SystemExit(1)


# ============================================================
# LOAD AUDIO
# ============================================================

print("\nLoading audio...")

audio, sr = librosa.load(
    AUDIO_PATH,
    sr=SAMPLE_RATE,
    mono=True
)

duration = len(audio) / SAMPLE_RATE

rms = np.sqrt(
    np.mean(
        audio.astype(np.float64) ** 2
    )
)

print(f"Original loaded SR : {SAMPLE_RATE} Hz")
print(f"Samples            : {len(audio)}")
print(f"Duration           : {duration:.2f} sec")
print(f"RMS                : {rms:.6f}")
print(f"Minimum            : {audio.min():.6f}")
print(f"Maximum            : {audio.max():.6f}")


# ============================================================
# GPU INFORMATION
# ============================================================

print("\n" + "=" * 70)
print("GPU")
print("=" * 70)

print(f"CUDA available : {torch.cuda.is_available()}")

if torch.cuda.is_available():

    print(
        f"GPU : "
        f"{torch.cuda.get_device_name(0)}"
    )

    print(
        f"VRAM : "
        f"{torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB"
    )


# ============================================================
# LOAD PARROTLET
# ============================================================

print("\n" + "=" * 70)
print("LOADING PARROTLET")
print("=" * 70)

load_start = time.time()

model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    device_map="auto",
)

model.eval()

load_time = time.time() - load_start

print(
    f"\nModel loaded in "
    f"{load_time:.2f} sec"
)


# ============================================================
# TRANSCRIBE RECORDING 4
# ============================================================

print("\n" + "=" * 70)
print("TRANSCRIBING RECORDING 4")
print("=" * 70)

print(f"Duration : {duration:.2f} sec")
print("Running Parrotlet...\n")

start = time.time()

try:

    transcript = model.transcribe(
        audio,
        SAMPLE_RATE
    )

    inference_time = time.time() - start

    rtf = inference_time / duration

    realtime_speed = duration / inference_time

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("PARROTLET TRANSCRIPTION")
    print("=" * 70)

    print("\n")
    print(transcript)
    print("\n")

    print("=" * 70)
    print("PERFORMANCE")
    print("=" * 70)

    print(
        f"Inference time : "
        f"{inference_time:.2f} sec"
    )

    print(
        f"RTF            : "
        f"{rtf:.3f}"
    )

    print(
        f"Real-time speed: "
        f"{realtime_speed:.2f}x"
    )

except Exception as e:

    print("\n" + "=" * 70)
    print("TRANSCRIPTION ERROR")
    print("=" * 70)

    print(type(e).__name__)
    print(str(e))

    raise


# ============================================================
# GPU MEMORY
# ============================================================

if torch.cuda.is_available():

    print("\n" + "=" * 70)
    print("GPU MEMORY AFTER TRANSCRIPTION")
    print("=" * 70)

    allocated = (
        torch.cuda.memory_allocated()
        / (1024 ** 3)
    )

    reserved = (
        torch.cuda.memory_reserved()
        / (1024 ** 3)
    )

    print(
        f"Allocated : {allocated:.2f} GB"
    )

    print(
        f"Reserved  : {reserved:.2f} GB"
    )


print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)