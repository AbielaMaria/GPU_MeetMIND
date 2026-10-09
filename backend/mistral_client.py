"""

MeetMind - Mistral 128B API Client

Uses an OpenAI-compatible chat-completions endpoint.

Features:

    - Loads configuration from the project-root .env file.

    - Retries transient HTTP errors (429, 500, 502, 503, 504).

    - Retries connection errors and request timeouts.

    - Uses exponential backoff between retry attempts.

    - Handles JSON and response-format errors.

    - Never logs the API key.

"""

from pathlib import Path

import os

import time

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

    "MISTRAL_API_URL", ""

).strip()

MISTRAL_API_KEY = os.getenv(

    "MISTRAL_API_KEY", ""

).strip()

MISTRAL_MODEL = os.getenv(

    "MISTRAL_MODEL", "mistral-128b"

).strip()

# Maximum total attempts, including the first request.

MAX_RETRIES = 3

# HTTP connection and response-read timeouts, in seconds.

CONNECT_TIMEOUT = 10

READ_TIMEOUT = 180

# Long-context configuration. 128K is the intended Mistral context window.

# Keep a small safety margin so the generated response can fit as well.

MISTRAL_CONTEXT_WINDOW = int(os.getenv("MISTRAL_CONTEXT_WINDOW", "128000"))

MISTRAL_CONTEXT_SAFETY_MARGIN = int(os.getenv("MISTRAL_CONTEXT_SAFETY_MARGIN", "2048"))

# Exponential backoff: 2 seconds, then 4 seconds.

INITIAL_RETRY_DELAY = 2

# Retry only errors that may be temporary.

RETRYABLE_STATUS_CODES = {

    429,

    500,

    502,

    503,

    504,

}

# ============================================================

# CONTEXT WINDOW VALIDATION

# ============================================================

def _estimate_tokens(text: str) -> int:
    """
    Estimate token usage without requiring a tokenizer.

    This is a safety estimate only; it is not an exact provider
    tokenizer count. A ~4 characters/token approximation is used.
    """
    if not text:
        return 0

    return max(1, (len(text) + 3) // 4)


def _validate_context_budget(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> None:
    """
    Validate that the requested prompt plus output fits within the
    configured Mistral context window.

    The previous version of this file called this function from
    call_mistral() but did not define it, causing:

        name '_validate_context_budget' is not defined
    """
    if max_tokens < 1:
        raise ValueError("max_tokens must be greater than 0.")

    system_tokens = _estimate_tokens(system_prompt)
    user_tokens = _estimate_tokens(user_prompt)

    estimated_prompt_tokens = system_tokens + user_tokens

    available_for_output = (
        MISTRAL_CONTEXT_WINDOW
        - MISTRAL_CONTEXT_SAFETY_MARGIN
        - estimated_prompt_tokens
    )

    estimated_total = estimated_prompt_tokens + max_tokens

    print()
    print("-" * 70)
    print("MISTRAL CONTEXT BUDGET")
    print("-" * 70)
    print("Context window:", MISTRAL_CONTEXT_WINDOW, "tokens")
    print("Safety margin:", MISTRAL_CONTEXT_SAFETY_MARGIN, "tokens")
    print("Estimated system tokens:", system_tokens)
    print("Estimated user tokens:", user_tokens)
    print("Estimated prompt tokens:", estimated_prompt_tokens)
    print("Requested output tokens:", max_tokens)
    print("Available output tokens:", max(0, available_for_output))
    print("Estimated total:", estimated_total)
    print("-" * 70)

    if available_for_output <= 0:
        raise RuntimeError(
            "Mistral context window exceeded before output generation. "
            f"Estimated prompt tokens: {estimated_prompt_tokens}, "
            f"context window: {MISTRAL_CONTEXT_WINDOW}, "
            f"safety margin: {MISTRAL_CONTEXT_SAFETY_MARGIN}."
        )

    if max_tokens > available_for_output:
        raise RuntimeError(
            "Mistral context window exceeded. "
            f"Estimated prompt tokens: {estimated_prompt_tokens}, "
            f"requested output tokens: {max_tokens}, "
            f"available output tokens after safety margin: "
            f"{available_for_output}, "
            f"context window: {MISTRAL_CONTEXT_WINDOW}."
        )


# ============================================================

# ============================================================

# CONFIGURATION VALIDATION

# ============================================================

def validate_mistral_config() -> None:

    """Validate the required Mistral API configuration."""

    if not MISTRAL_API_URL:

        raise RuntimeError(

            "MISTRAL_API_URL is missing from the project .env file."

        )

    if not MISTRAL_API_KEY:

        raise RuntimeError(

            "MISTRAL_API_KEY is missing from the project .env file."

        )

    if not MISTRAL_MODEL:

        raise RuntimeError(

            "MISTRAL_MODEL is missing from the project .env file."

        )

# ============================================================

# ERROR RESPONSE HELPER

# ============================================================

def _get_error_details(response: requests.Response) -> str:

    """Extract a bounded error message without exposing credentials."""

    body = (response.text or "").strip()

    if not body:

        body = "The API returned an empty error response."

    # Avoid dumping a large HTML gateway error into the frontend.

    return body[:1000]

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

        Assistant response as a string.

    Raises:

        RuntimeError: If configuration, networking, HTTP,

                      JSON, or response validation fails.

    """

    validate_mistral_config()

    _validate_context_budget(system_prompt, user_prompt, max_tokens)

    headers = {

        "Authorization": f"Bearer {MISTRAL_API_KEY}",

        "Content-Type": "application/json",

    }

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

    timeout = (CONNECT_TIMEOUT, READ_TIMEOUT)

    print()

    print("=" * 70)

    print("MEETMIND - MISTRAL API REQUEST")

    print("=" * 70)

    print("Model:", MISTRAL_MODEL)

    print("Endpoint:", MISTRAL_API_URL)

    print("Maximum attempts:", MAX_RETRIES)

    print("Read timeout:", READ_TIMEOUT, "seconds")

    print("Context window:", MISTRAL_CONTEXT_WINDOW, "tokens")

    print("=" * 70)

    last_error = None

    # ========================================================

    # REQUEST + RETRY LOOP

    # ========================================================

    for attempt in range(1, MAX_RETRIES + 1):

        print(

            f"[Mistral] Request attempt "

            f"{attempt}/{MAX_RETRIES}"

        )

        try:

            response = requests.post(

                MISTRAL_API_URL,

                headers=headers,

                json=payload,

                timeout=timeout,

            )

        except requests.exceptions.Timeout as exc:

            last_error = (

                "Mistral API request timed out "

                f"(connect={CONNECT_TIMEOUT}s, "

                f"read={READ_TIMEOUT}s)."

            )

            print(f"[Mistral] Timeout: {last_error}")

        except requests.exceptions.ConnectionError as exc:

            last_error = (

                "Could not connect to the Mistral API endpoint."

            )

            print(f"[Mistral] Connection error: {exc}")

        except requests.exceptions.RequestException as exc:

            # Other request errors are not automatically retried.

            raise RuntimeError(

                f"Mistral API request failed: {exc}"

            ) from exc

        else:

            # ================================================

            # HTTP ERROR HANDLING

            # ================================================

            if not response.ok:

                status_code = response.status_code

                error_details = _get_error_details(response)

                last_error = (

                    f"Mistral API returned HTTP {status_code}: "

                    f"{error_details}"

                )

                print(

                    f"[Mistral] HTTP {status_code} "

                    f"on attempt {attempt}/{MAX_RETRIES}"

                )

                if status_code not in RETRYABLE_STATUS_CODES:

                    raise RuntimeError(last_error)

                # Retry-After is optional and may be absent or invalid.

                retry_after = response.headers.get("Retry-After")

                response.close()

                if attempt < MAX_RETRIES:

                    delay = INITIAL_RETRY_DELAY * (2 ** (attempt - 1))

                    if retry_after:

                        try:

                            delay = max(

                                delay,

                                min(float(retry_after), 15.0),

                            )

                        except (ValueError, TypeError):

                            pass

                    print(

                        f"[Mistral] Temporary HTTP error. "

                        f"Retrying in {delay:g} seconds..."

                    )

                    time.sleep(delay)

                    continue

                raise RuntimeError(

                    f"{last_error} "

                    f"All {MAX_RETRIES} attempts failed."

                )

            # ================================================

            # JSON RESPONSE

            # ================================================

            try:

                data = response.json()

            except ValueError as exc:

                response.close()

                # A successful HTTP response with invalid JSON

                # is not assumed to be a transient gateway error.

                raise RuntimeError(

                    "Mistral API returned invalid JSON. "

                    f"Response: {response.text[:1000]}"

                ) from exc

            finally:

                response.close()

            # ================================================

            # EXTRACT ASSISTANT CONTENT

            # ================================================

            try:

                choices = data["choices"]

                if not choices:

                    raise ValueError("The choices array is empty.")

                message = choices[0]["message"]

                content = message["content"]

            except (KeyError, IndexError, TypeError, ValueError) as exc:

                raise RuntimeError(

                    "Unexpected Mistral API response format. "

                    f"Response: {str(data)[:1500]}"

                ) from exc

            # Some compatible endpoints return content blocks.

            if isinstance(content, list):

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

                raise RuntimeError(

                    "Mistral returned an unsupported response "

                    f"content type: {type(content).__name__}"

                )

            content = content.strip()

            if not content:

                raise RuntimeError(

                    "Mistral returned an empty response."

                )

            # ================================================

            # SUCCESS

            # ================================================

            print()

            print("=" * 70)

            print("MISTRAL API RESPONSE RECEIVED")

            print("=" * 70)

            print("Model:", MISTRAL_MODEL)

            print("Successful attempt:", attempt)

            print("Response length:", len(content), "characters")

            print("=" * 70)

            return content

        # ================================================

        # RETRY NETWORK ERRORS

        # ================================================

        if attempt < MAX_RETRIES:

            delay = INITIAL_RETRY_DELAY * (2 ** (attempt - 1))

            print(

                f"[Mistral] Retrying network failure "

                f"in {delay} seconds..."

            )

            time.sleep(delay)

    # ========================================================

    # ALL ATTEMPTS FAILED

    # ========================================================

    raise RuntimeError(

        f"Mistral API failed after {MAX_RETRIES} attempts. "

        f"Last error: {last_error or 'Unknown error'}"

    )
