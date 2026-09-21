from meeting_intelligence import generate_meeting_summary


transcript = """
Today we discussed the MeetMind project and the next development activities.

The team agreed that the current Mistral 128B API will be used for meeting
summarization instead of the local Ollama model.

The frontend integration is already working. We need to complete testing
of the summary generation and verify that the generated output contains the
meeting title, objective, summary, tasks, decisions, objections, and action
items.

Abiela will test the complete summarization flow and verify the frontend
display. The backend team will verify the Mistral API integration.

The team decided to complete the testing by Friday.
"""


print("=" * 70)
print("TESTING MEETING SUMMARY WITH MISTRAL 128B")
print("=" * 70)

try:
    result = generate_meeting_summary(transcript)

    print("\n" + "=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print("\nTITLE:")
    print(result["title"])

    print("\nOBJECTIVE:")
    print(result["objective"])

    print("\nMEETING SUMMARY:")
    print(result["meeting_summary"])

    print("\nTASKS ASSIGNED:")
    for task in result["tasks_assigned"]:
        print(task)

    print("\nDECISION POINTS:")
    for decision in result["decision_points"]:
        print("-", decision)

    print("\nOBJECTIONS:")
    for objection in result["objections"]:
        print("-", objection)

    print("\nACTION ITEMS:")
    for action in result["action_items"]:
        print("-", action)

    print("\nTIMELINE:")
    for item in result.get("timeline", []):
        print(item)

    print("\n" + "=" * 70)

except Exception as e:
    print("\n" + "=" * 70)
    print("MEETING SUMMARY TEST FAILED")
    print("=" * 70)
    print(type(e).__name__)
    print(str(e))
    print("=" * 70)