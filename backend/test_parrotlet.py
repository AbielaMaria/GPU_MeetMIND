import torch
import soundfile as sf
import librosa
from transformers import AutoModel


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_ID = "ekacare/parrotlet-a-2.5-pro"

AUDIO_PATH = (
    r"F:\MeetNotes\MeetNotes\meetmind_benchmark\audio\tamil_01w.wav"
)

# Parrotlet expects 16 kHz audio
SAMPLE_RATE = 16000

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("MEETMIND - PARROTLET-A 2.5 PRO TEST")
print("=" * 70)

print("Model       :", MODEL_ID)
print("Audio       :", AUDIO_PATH)
print("Sample rate :", SAMPLE_RATE)
print("Device      :", DEVICE)


# ============================================================
# LOAD MODEL
# ============================================================

print("\n" + "=" * 70)
print("LOADING MODEL")
print("=" * 70)

try:

    model = AutoModel.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
        device_map="auto"
    )

    model.eval()

    print("\nModel loaded")
    print("Model type:", type(model))
    print(
        "Model sampling rate:",
        getattr(model, "sampling_rate", "N/A")
    )
    print("Target SAMPLE_RATE:", SAMPLE_RATE)

except Exception as e:

    print("\nMODEL LOADING ERROR")
    print("Error type:", type(e).__name__)
    print("Error:", e)

    raise


# ============================================================
# PATCH 1:
# FIX PARROTLET preprocess_audio()
#
# Original model code contains:
#
#     target_sr=sampling_rate
#
# but `sampling_rate` is not defined.
#
# We explicitly use SAMPLE_RATE = 16000.
# ============================================================

print("\n" + "=" * 70)
print("PATCHING AUDIO PREPROCESSING")
print("=" * 70)


def fixed_preprocess_audio(audio_data, orig_sr):

    if orig_sr != SAMPLE_RATE:

        print(
            f"Internal resampling: "
            f"{orig_sr} Hz -> {SAMPLE_RATE} Hz"
        )

        audio_data = librosa.resample(
            audio_data,
            orig_sr=orig_sr,
            target_sr=SAMPLE_RATE,
            res_type="soxr_vhq"
        )

    return audio_data


model.preprocess_audio = fixed_preprocess_audio

print("preprocess_audio patched successfully")
print("Target sample rate:", SAMPLE_RATE)


# ============================================================
# PATCH 2:
# FIX PARROTLET transcribe()
#
# The original implementation does:
#
#     device = gen_kwargs.get(...)
#
# and eventually passes `device` into:
#
#     self.decoder.generate(...)
#
# Transformers generate() rejects that argument.
#
# Therefore we reproduce the official transcribe() logic here,
# but NEVER pass `device` to decoder.generate().
# ============================================================

print("\n" + "=" * 70)
print("PATCHING TRANSCRIPTION")
print("=" * 70)


def fixed_transcribe(
    audio,
    orig_sr,
    max_new_tokens=256,
    repetition_penalty=1.2,
    **gen_kwargs
):

    # --------------------------------------------------------
    # Determine device
    # --------------------------------------------------------

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    # --------------------------------------------------------
    # Remove device if accidentally supplied
    #
    # This prevents it from reaching decoder.generate().
    # --------------------------------------------------------

    gen_kwargs.pop("device", None)

    # --------------------------------------------------------
    # Get model prompt
    # --------------------------------------------------------

    prompt = model.get_prompt()

    # --------------------------------------------------------
    # Tokenize prompt
    # --------------------------------------------------------

    input_ids = torch.tensor(
        model.tokenizer(
            prompt,
            add_special_tokens=False
        )["input_ids"]
    )

    input_attention_mask = torch.ones_like(input_ids)

    # --------------------------------------------------------
    # Locate audio token
    # --------------------------------------------------------

    audio_token = model.tokenizer.convert_tokens_to_ids(
        model.audio_token
    )

    input_ids_list = input_ids.tolist()

    if audio_token not in input_ids_list:

        raise ValueError(
            "Audio token was not found in the Parrotlet prompt."
        )

    audio_pos = input_ids_list.index(audio_token)

    # --------------------------------------------------------
    # Move text inputs to GPU
    # --------------------------------------------------------

    input_ids = input_ids.unsqueeze(0).to(device)

    input_attention_mask = (
        input_attention_mask
        .unsqueeze(0)
        .to(device)
    )

    # --------------------------------------------------------
    # Preprocess audio
    # --------------------------------------------------------

    processed_audio = model.preprocess_audio(
        audio,
        orig_sr
    )

    # --------------------------------------------------------
    # Extract audio features
    # --------------------------------------------------------

    audio_features = model.processor.feature_extractor(
        [processed_audio],
        sampling_rate=model.sampling_rate,
        return_tensors="pt"
    ).input_features

    audio_features = audio_features.to(device)

    # --------------------------------------------------------
    # Audio encoder
    # --------------------------------------------------------

    with torch.no_grad():

        audio_embeddings = (
            model.encoder(audio_features)
            .last_hidden_state
        )

        projected_audio_embeddings = (
            model.projector(audio_embeddings)
        )

    # --------------------------------------------------------
    # Text embeddings
    # --------------------------------------------------------

    input_embeddings = (
        model.decoder
        .get_input_embeddings()(input_ids)
    )

    batch_size, input_seq_len, embed_dim = (
        input_embeddings.shape
    )

    audio_seq_len = (
        projected_audio_embeddings.shape[1]
    )

    # --------------------------------------------------------
    # Combine text + audio embeddings
    # --------------------------------------------------------

    max_combined_len = (
        input_seq_len
        + audio_seq_len
        - 1
    )

    combined_embeddings = torch.zeros(
        batch_size,
        max_combined_len,
        embed_dim,
        device=device,
        dtype=input_embeddings.dtype
    )

    combined_attention_mask = torch.zeros(
        batch_size,
        max_combined_len,
        device=device,
        dtype=input_attention_mask.dtype
    )

    # --------------------------------------------------------
    # Prefix before audio token
    # --------------------------------------------------------

    combined_embeddings[:, :audio_pos] = (
        input_embeddings[:, :audio_pos]
    )

    combined_attention_mask[:, :audio_pos] = (
        input_attention_mask[:, :audio_pos]
    )

    # --------------------------------------------------------
    # Insert audio embeddings
    # --------------------------------------------------------

    combined_embeddings[
        :,
        audio_pos:audio_pos + audio_seq_len
    ] = projected_audio_embeddings

    combined_attention_mask[
        :,
        audio_pos:audio_pos + audio_seq_len
    ] = 1

    # --------------------------------------------------------
    # Suffix after audio token
    # --------------------------------------------------------

    suffix_start = audio_pos + 1

    suffix_len = (
        input_seq_len
        - suffix_start
    )

    out_start = (
        audio_pos
        + audio_seq_len
    )

    combined_embeddings[
        :,
        out_start:out_start + suffix_len
    ] = input_embeddings[
        :,
        suffix_start:
    ]

    combined_attention_mask[
        :,
        out_start:out_start + suffix_len
    ] = input_attention_mask[
        :,
        suffix_start:
    ]

    # --------------------------------------------------------
    # Generation arguments
    #
    # IMPORTANT:
    # NO `device` HERE.
    # --------------------------------------------------------

    default_gen_kwargs = {

        "max_new_tokens": max_new_tokens,

        "do_sample": False,

        "repetition_penalty": repetition_penalty,

        "pad_token_id": (
            model.tokenizer.pad_token_id
        ),

        "eos_token_id": (
            model.tokenizer.eos_token_id
        )
    }

    # Add any additional generation arguments.
    #
    # `device` was already removed above.
    default_gen_kwargs.update(gen_kwargs)

    # --------------------------------------------------------
    # Generate transcription
    # --------------------------------------------------------

    with torch.no_grad():

        outputs = model.decoder.generate(

            inputs_embeds=combined_embeddings,

            attention_mask=combined_attention_mask,

            **default_gen_kwargs
        )

    # --------------------------------------------------------
    # Decode
    # --------------------------------------------------------

    text = model.tokenizer.decode(
        outputs[0],
        skip_special_tokens=True
    ).strip()

    return text


model.transcribe = fixed_transcribe

print("transcribe() patched successfully")
print("device will NOT be passed to decoder.generate()")


# ============================================================
# LOAD AUDIO
# ============================================================

print("\n" + "=" * 70)
print("LOADING AUDIO")
print("=" * 70)

print("Audio file:", AUDIO_PATH)

try:

    audio, orig_sr = sf.read(AUDIO_PATH)

except Exception as e:

    print("\nAUDIO LOADING ERROR")
    print("Error type:", type(e).__name__)
    print("Error:", e)

    raise


print("Original sample rate:", orig_sr)
print("Original audio shape:", audio.shape)
print("Target sample rate:", SAMPLE_RATE)


# ============================================================
# CONVERT STEREO TO MONO
# ============================================================

if len(audio.shape) > 1:

    print("Stereo audio detected -> converting to mono")

    audio = audio.mean(axis=1)

else:

    print("Audio is already mono")


# ============================================================
# RESAMPLE TO 16 kHz
# ============================================================

if orig_sr != SAMPLE_RATE:

    print(
        f"Resampling audio: "
        f"{orig_sr} Hz -> {SAMPLE_RATE} Hz"
    )

    audio = librosa.resample(
        audio,
        orig_sr=orig_sr,
        target_sr=SAMPLE_RATE,
        res_type="soxr_vhq"
    )

else:

    print("Audio already at 16000 Hz")


# ============================================================
# FINAL AUDIO INFORMATION
# ============================================================

print("Final audio shape:", audio.shape)
print("Final sample rate:", SAMPLE_RATE)

duration = len(audio) / SAMPLE_RATE

print(
    "Audio duration:",
    round(duration, 2),
    "seconds"
)


# ============================================================
# TRANSCRIBE
# ============================================================

print("\n" + "=" * 70)
print("TRANSCRIBING")
print("=" * 70)

try:

    with torch.no_grad():

        transcription = model.transcribe(

            audio,

            SAMPLE_RATE,

            max_new_tokens=256,

            repetition_penalty=1.2

        )

    print("\n" + "=" * 70)
    print("TRANSCRIPTION")
    print("=" * 70)

    print()

    if transcription:

        print(transcription)

    else:

        print("[EMPTY TRANSCRIPTION]")

    print()

except Exception as e:

    print("\n" + "=" * 70)
    print("TRANSCRIPTION ERROR")
    print("=" * 70)

    print("Error type:", type(e).__name__)
    print("Error:", e)

    import traceback

    traceback.print_exc()


# ============================================================
# GPU INFORMATION
# ============================================================

print("\n" + "=" * 70)
print("GPU INFORMATION")
print("=" * 70)

if torch.cuda.is_available():

    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )

    print(
        "GPU memory allocated:",
        round(
            torch.cuda.memory_allocated() /
            (1024 ** 3),
            2
        ),
        "GB"
    )

    print(
        "GPU memory reserved:",
        round(
            torch.cuda.memory_reserved() /
            (1024 ** 3),
            2
        ),
        "GB"
    )

else:

    print("CUDA is not available")


# ============================================================
# END
# ============================================================

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)