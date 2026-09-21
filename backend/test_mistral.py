from mistral_client import (
    call_mistral,
    MISTRAL_MODEL,
)


print("=" * 70)
print("TESTING MISTRAL CLIENT")
print("=" * 70)

print("Model:", MISTRAL_MODEL)


try:

    response = call_mistral(
        system_prompt=(
            "You are a helpful AI assistant."
        ),

        user_prompt=(
            "Explain what MeetMind is in one short sentence."
        ),

        temperature=0.0,

        max_tokens=100,
    )

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print("Mistral response:")
    print(response)

    print("=" * 70)


except Exception as exc:

    print()
    print("=" * 70)
    print("MISTRAL TEST FAILED")
    print("=" * 70)

    print(type(exc).__name__)
    print(str(exc))

    print("=" * 70)