import os
import time
import types
import torch
import librosa
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

MODEL_NAME = "ekacare/parrotlet-a-2.5-pro"

AUDIO_FILE = r"F:\MeetNotes\MeetNotes\backend\Recording 5.wav"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# FIX Parrotlet preprocess_audio()
# ============================================================

def fixed_preprocess_audio(self, audio_data, orig_sr):
    """
    Fixed version of Parrotlet's preprocess_audio().

    Original code has:
        target_sr=sampling_rate

    which is undefined.

    Correct:
        target_sr=self.sampling_rate
    """
    if orig_sr != self.sampling_rate:
        audio_data = librosa.resample(
            audio_data,
            orig_sr=orig_sr,
            target_sr=self.sampling_rate,
            res_type="soxr_vhq",
        )

    return audio_data


# ============================================================
# GPU MEMORY
# ============================================================

def print_gpu_memory(label):
    if not torch.cuda.is_available():
        return

    torch.cuda.synchronize()

    free, total = torch.cuda.mem_get_info()

    allocated = torch.cuda.memory_allocated()
    reserved = torch.cuda.memory_reserved()

    print(f"\n========== GPU MEMORY: {label} ==========")
    print(f"Physical total     : {total / 1024**3:.2f} GB")
    print(f"Physical free      : {free / 1024**3:.2f} GB")
    print(f"PyTorch allocated  : {allocated / 1024**3:.2f} GB")
    print(f"PyTorch reserved   : {reserved / 1024**3:.2f} GB")


# ============================================================
# LOAD MODEL
# ============================================================

print("\n========================================")
print("Loading Parrotlet")
print("========================================")

print("Model :", MODEL_NAME)
print("Device:", DEVICE)

load_start = time.perf_counter()

model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    dtype=torch.float16,
)

load_time = time.perf_counter() - load_start

print(f"\nModel loaded in {load_time:.2f} seconds")

print_gpu_memory("AFTER MODEL LOAD")


# ============================================================
# SHOW MODEL COMPONENT DTYPES / DEVICES
# ============================================================

print("\n========================================")
print("MODEL COMPONENTS")
print("========================================")

components = {
    "encoder": model.encoder,
    "projector": model.projector,
    "decoder": model.decoder,
}

for name, component in components.items():

    try:
        parameter = next(component.parameters())

        print(
            f"{name:10s} | "
            f"device={parameter.device} | "
            f"dtype={parameter.dtype}"
        )

    except StopIteration:
        print(f"{name:10s} | no parameters")


# ============================================================
# APPLY preprocess_audio FIX
# ============================================================

model.preprocess_audio = types.MethodType(
    fixed_preprocess_audio,
    model
)

print("\npreprocess_audio() fix applied.")


# ============================================================
# LOAD AUDIO
# ============================================================

print("\n========================================")
print("LOADING AUDIO")
print("========================================")

audio, sr = librosa.load(
    AUDIO_FILE,
    sr=None,
    mono=True,
)

duration = len(audio) / sr

print(f"Audio sample rate : {sr} Hz")
print(f"Audio duration    : {duration:.2f} seconds")
print(f"Audio samples     : {len(audio):,}")


# ============================================================
# USE FIRST 30 SECONDS
# ============================================================

TEST_DURATION = 30.0

test_samples = min(
    len(audio),
    int(TEST_DURATION * sr)
)

test_audio = audio[:test_samples]

test_duration = len(test_audio) / sr

print(f"\nTesting duration  : {test_duration:.2f} seconds")


# ============================================================
# TRANSCRIPTION
# ============================================================

print("\n========================================")
print("RUNNING TRANSCRIPTION")
print("========================================")

if torch.cuda.is_available():
    torch.cuda.synchronize()

start = time.perf_counter()

try:

    text = model.transcribe(
        test_audio,
        sr,
        max_new_tokens=256,
        repetition_penalty=1.2,
    )

except Exception as e:

    print("\n❌ TRANSCRIPTION FAILED")
    print(type(e).__name__, ":", e)

    print_gpu_memory("AFTER FAILURE")

    raise

if torch.cuda.is_available():
    torch.cuda.synchronize()

inference_time = time.perf_counter() - start


# ============================================================
# RESULTS
# ============================================================

rtf = inference_time / test_duration
speed = test_duration / inference_time

print("\n========================================")
print("RESULT")
print("========================================")

print(f"Audio duration : {test_duration:.2f} sec")
print(f"Inference time : {inference_time:.2f} sec")
print(f"RTF            : {rtf:.3f}")
print(f"Speed          : {speed:.2f}x realtime")

print("\nTRANSCRIPTION:")
print("----------------------------------------")
print(text)
print("----------------------------------------")

print_gpu_memory("AFTER TRANSCRIPTION")