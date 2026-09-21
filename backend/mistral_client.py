"""
MeetMind - Mistral 128B API Client

Uses an OpenAI-compatible chat-completions endpoint:

    POST <MISTRAL_API_URL>

with:

    Authorization: Bearer <API_KEY>
    Content-Type: application/json

The actual endpoint and API key are loaded from the project-root
.env file.
"""

from pathlib import Path
import os
import requests
from dotenv import load_dotenv


# ============================================================
# LOAD PROJECT ROOT .ENV
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


# ============================================================
# CONFIGURATION
# ============================================================

MISTRAL_API_URL = os.getenv(
    "MISTRAL_API_URL",
    "",
).strip()

MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY",
    "",
).strip()

MISTRAL_MODEL = os.getenv(
    "MISTRAL_MODEL",
    "mistral-128b",
).strip()


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

def validate_mistral_config() -> None:
    """
    Validate the required Mistral configuration.

    Raises:
        RuntimeError: If any required setting is missing.
    """

    if not MISTRAL_API_URL:
        raise RuntimeError(
            "MISTRAL_API_URL is not configured in the project .env file."
        )

    if not MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY is not configured in the project .env file."
        )

    if not MISTRAL_MODEL:
        raise RuntimeError(
            "MISTRAL_MODEL is not configured in the project .env file."
        )


# ============================================================
# MISTRAL API CALL
# ============================================================

def call_mistral(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """
    Send a chat-completion request to the configured Mistral API.

    Args:
        system_prompt: MeetMind system instructions.
        user_prompt: Meeting transcript and task instructions.
        temperature: Sampling temperature.
        max_tokens: Maximum generated tokens.

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: For configuration, network, HTTP, JSON,
                      or response-format errors.
    """

    validate_mistral_config()

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    # OpenAI-compatible chat-completions payload.
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    print()
    print("=" * 70)
    print("MEETMIND - MISTRAL API REQUEST")
    print("=" * 70)
    print("LLM Model:", MISTRAL_MODEL)
    print("Endpoint:", MISTRAL_API_URL)
    print("=" * 70)

    try:
        response = requests.post(
            MISTRAL_API_URL,
            headers=headers,
            json=payload,
            timeout=180,
        )

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Mistral API request timed out after 180 seconds."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Could not connect to the Mistral API endpoint."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Mistral API request failed: {exc}"
        ) from exc

    # ========================================================
    # HTTP ERROR
    # ========================================================

    if not response.ok:
        response_text = response.text[:3000]

        raise RuntimeError(
            "Mistral API returned "
            f"HTTP {response.status_code}: "
            f"{response_text}"
        )

    # ========================================================
    # JSON RESPONSE
    # ========================================================

    try:
        data = response.json()

    except ValueError as exc:
        raise RuntimeError(
            "Mistral API returned invalid JSON. "
            f"Response: {response.text[:2000]}"
        ) from exc

    # ========================================================
    # EXTRACT ASSISTANT CONTENT
    # ========================================================

    try:
        content = (
            data["choices"][0]
            ["message"]
            ["content"]
        )

    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "Unexpected Mistral API response format. "
            f"Response: {data}"
        ) from exc

    if isinstance(content, list):
        # Some OpenAI-compatible APIs may return content blocks.
        text_parts = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    text_parts.append(str(text))
            elif isinstance(item, str):
                text_parts.append(item)

        content = "\n".join(text_parts)

    if not isinstance(content, str):
        content = str(content)

    content = content.strip()

    if not content:
        raise RuntimeError(
            "Mistral returned an empty response."
        )

    print()
    print("=" * 70)
    print("MISTRAL API RESPONSE RECEIVED")
    print("=" * 70)
    print("Response length:", len(content), "characters")
    print("=" * 70)

    return content
