# """
# MeetMind - Meeting Intelligence

# Flow:

# Complete transcript
#         |
#         v
# Llama 3.1 8B via Ollama
#         |
#         v
# Structured meeting intelligence

# Speaker diarization: DISABLED
# """

# import os
# import re
# from typing import Optional

# from ollama import chat
# from pydantic import BaseModel


# # ============================================================
# # CONFIGURATION
# # ============================================================

# LLAMA_MODEL = os.getenv(
#     "MEETMIND_LLAMA_MODEL",
#     "llama3.1:8b",
# )


# # ============================================================
# # PLACEHOLDER / REFUSAL DETECTION
# # ============================================================

# _PLACEHOLDER_VALUES = {
#     "unknown",
#     "not mentioned",
#     "not specified",
#     "n/a",
#     "none",
#     "null",
#     "",
# }

# _REFUSAL_PATTERNS = (
#     "could not be generated",
#     "could not be determined",
#     "cannot be determined",
#     "unable to determine",
#     "no objective",
#     "no objective found",
#     "not mentioned",
#     "not specified",
#     "unknown",
# )


# def _looks_like_refusal(text: str) -> bool:
#     text = (text or "").strip().lower()

#     if not text:
#         return True

#     return any(
#         pattern in text
#         for pattern in _REFUSAL_PATTERNS
#     )


# # ============================================================
# # NAME VALIDATION
# # ============================================================

# _PRONOUN_STARTS = (
#     "i ",
#     "i'll",
#     "i will",
#     "i'm",
#     "we ",
#     "we'll",
#     "we will",
#     "we're",
#     "you ",
#     "you'll",
#     "they ",
#     "he ",
#     "she ",
#     "it ",
# )

# _TASK_VERB_PATTERN = re.compile(
#     r"\b("
#     r"will|test|check|review|update|send|do|complete|"
#     r"finish|verify|fix|build|create|write|prepare|"
#     r"evaluate|develop|integrate|implement|analyze|analyse"
#     r")\b",
#     re.IGNORECASE,
# )


# def _looks_like_real_name(value: str) -> bool:
#     value = (value or "").strip()

#     if not value:
#         return False

#     lowered = value.lower()

#     if lowered in _PLACEHOLDER_VALUES:
#         return False

#     if lowered.startswith(_PRONOUN_STARTS):
#         return False

#     # A person's name should not be an entire sentence.
#     if len(value.split()) > 3:
#         return False

#     # Prevent task fragments such as:
#     # "I'll test"
#     # "will evaluate"
#     if _TASK_VERB_PATTERN.search(lowered):
#         return False

#     return True


# # ============================================================
# # PYDANTIC OUTPUT SCHEMA
# # ============================================================

# class Task(BaseModel):
#     task: str
#     assignee: Optional[str] = None
#     deadline: Optional[str] = None


# class TimelineItem(BaseModel):
#     action: str
#     date: str


# class MeetingResult(BaseModel):
#     title: str
#     objective: str
#     meeting_summary: str
#     tasks_assigned: list[Task]
#     decision_points: list[str]
#     objections: list[str]
#     action_items: list[str]
#     timeline: list[TimelineItem]


# # ============================================================
# # SYSTEM PROMPT
# # ============================================================

# SYSTEM_PROMPT = """
# You are MeetMind, an AI meeting intelligence system.

# Your job is to analyze the COMPLETE meeting transcript and
# produce accurate, useful, professional meeting intelligence.

# The transcript may contain:

# - English
# - Tamil
# - Tamil-English code-mixed speech
# - Indian English
# - informal spoken language
# - automatic speech recognition errors

# Speaker diarization is DISABLED.

# Do not create speaker labels.


# ============================================================
# STRICT TRANSCRIPT GROUNDING
# ============================================================

# Use ONLY information supported by the transcript.

# Never invent:

# - names
# - people
# - tasks
# - assignees
# - deadlines
# - dates
# - decisions
# - objections
# - action items
# - facts

# You may correct an obvious ASR error only when the intended
# meaning is clear from the surrounding context.


# ============================================================
# 1. TITLE
# ============================================================

# Generate a short, meaningful title based on the actual meeting.

# The title should describe the main subject of the meeting.

# Avoid generic titles such as:

# "Meeting"
# "Project Meeting"
# "Discussion"

# when a more specific title can be generated.


# ============================================================
# 2. OBJECTIVE
# ============================================================

# The objective is MANDATORY.

# Analyze the COMPLETE transcript and determine WHY the meeting
# was held.

# The speaker does not need to explicitly say:

# "The objective is..."

# Infer the purpose from:

# - what is being reviewed
# - what is being tested
# - what problem is being addressed
# - what the participants are trying to accomplish
# - what outcome the meeting is working toward

# Example:

# Transcript:

# "Today we are testing the Parrotlet speech recognition system.
# We want to verify whether the complete recording is transcribed
# correctly."

# Objective:

# "Verify the accuracy and completeness of the Parrotlet
# transcription system."

# The objective must:

# - be specific
# - be concise
# - explain why the meeting happened
# - be based on the complete transcript
# - be generated through analysis

# NEVER return:

# "Objective could not be determined."
# "No objective found."
# "No objective could be generated."
# "Not mentioned."
# "Unknown."

# Even when the objective is not explicitly stated, infer the
# most reasonable purpose from the complete discussion.


# ============================================================
# 3. MEETING SUMMARY
# ============================================================

# Generate a PROFESSIONAL EXECUTIVE-STYLE SUMMARY.

# Do NOT simply shorten or copy the transcript.

# The summary must explain:

# 1. What the meeting was primarily about.
# 2. The important topics discussed.
# 3. The current status or progress.
# 4. Problems, concerns, limitations, or gaps.
# 5. Important decisions.
# 6. Planned next steps.

# The summary should allow someone who did NOT attend the meeting
# to understand what happened.

# When applicable, clearly distinguish:

# - CURRENT STATUS
# - KEY DISCUSSION
# - PROBLEMS / GAPS
# - DECISIONS
# - NEXT STEPS

# Do not invent information.

# Preserve important technical terminology.

# For a normal meeting, produce approximately 3-6 sentences.

# For a short meeting, use fewer sentences.

# For a long meeting, provide enough detail to cover the major
# outcomes without becoming repetitive.

# The summary should read like a professional meeting report,
# not like a transcript.


# ============================================================
# 4. TASKS
# ============================================================

# Extract only genuine work that needs to be completed.

# Do not convert every statement into a task.

# Example:

# "We discussed database integration."

# This is discussion, not necessarily a task.

# Example:

# "We need to integrate the backend database."

# This is a task.

# Tasks must represent actual work.


# ============================================================
# 5. TASK ASSIGNEE
# ============================================================

# Only provide an assignee when a person's NAME is explicitly
# identified as responsible for the task.

# Example:

# "Ravi will evaluate the transcription quality."

# Correct:

# task:
# "Evaluate the transcription quality"

# assignee:
# "Ravi"

# If the transcript says:

# "I will evaluate the transcription quality."

# DO NOT use:

# "I"
# "I'll"
# "I'll test"
# "will evaluate"

# as the assignee.

# In that case:

# assignee = null

# The assignee field is ONLY for a person's name.


# ============================================================
# 6. DEADLINE
# ============================================================

# Only provide a deadline when the transcript explicitly states
# a deadline or date for the task.

# Examples:

# "I will complete this by Friday."

# deadline = "Friday"

# "We will finish it next week."

# deadline = "next week"

# "Let's test the recordings on September 5."

# deadline = "September 5"

# "The demo needs to be ready tomorrow."

# deadline = "tomorrow"

# If no deadline or date is explicitly stated:

# deadline = null

# Never infer or invent a deadline.

# Do NOT convert general future language such as:

# - "later"
# - "soon"
# - "in the future"
# - "after this"
# - "next step"

# into a deadline unless the transcript gives a specific
# time/date reference.


# ============================================================
# 7. TIMELINE
# ============================================================

# The Timeline is a separate section containing ONLY actions
# that have an explicitly mentioned deadline or date in the
# meeting transcript.

# Timeline format:

# | S.No | Action | Date |

# Rules:

# 1. Include ONLY actions with an explicitly mentioned deadline
#    or date.

# 2. The action must correspond to an actual task/action discussed
#    in the transcript.

# 3. Use the explicitly stated date/deadline.

# 4. Do NOT invent dates.

# 5. Do NOT infer dates from context.

# 6. Do NOT include tasks without a deadline.

# 7. Do NOT include general discussion points.

# 8. Do NOT include decisions unless they also represent an
#    explicit action with a stated deadline.

# Example:

# Transcript:

# "Ravi will test the Tamil demo videos by Friday."

# Timeline:

# action:
# "Test the Tamil demo videos"

# date:
# "Friday"

# Example:

# Transcript:

# "We need to test additional recordings."

# There is no date.

# Therefore:

# timeline = []

# Example:

# Transcript:

# "We need to test additional recordings by September 5."

# Timeline:

# action:
# "Test additional recordings"

# date:
# "September 5"

# If no action with a specific deadline/date is mentioned:

# timeline = []


# ============================================================
# 8. DECISIONS
# ============================================================

# Extract only decisions that were actually made.

# Example:

# "We decided to continue testing both Tamil and English audio."

# This is a decision.

# Example:

# "We discussed testing Tamil and English audio."

# This is discussion, not necessarily a decision.

# If there are no actual decisions:

# return []


# ============================================================
# 9. OBJECTIONS / CONCERNS
# ============================================================

# Extract genuine:

# - objections
# - disagreements
# - concerns
# - reservations
# - blockers
# - explicitly raised risks

# Example:

# "I'm concerned that longer recordings may cause memory problems."

# This is a concern.

# Do not invent objections simply because a problem was discussed.

# If no genuine objection or concern exists:

# return []


# ============================================================
# 10. ACTION ITEMS
# ============================================================

# Extract explicit follow-up actions resulting from the meeting.

# Example:

# "The action item is to test longer audio and verify the results."

# Return:

# "Test longer audio and verify the results"

# Do not invent action items.

# If none exist:

# return []


# ============================================================
# 11. TASKS VS ACTION ITEMS
# ============================================================

# Avoid unnecessary duplication.

# TASK:
# Work that needs to be completed.

# ACTION ITEM:
# An explicit follow-up action resulting from the meeting.

# Use judgment when the same statement could fit both categories.


# ============================================================
# 12. TIMELINE VS DEADLINE
# ============================================================

# The task object may contain a deadline.

# The Timeline is a separate presentation of ONLY those tasks
# that have an explicitly stated deadline/date.

# For example:

# tasks_assigned:

# [
#     {
#         "task": "Test additional recordings",
#         "assignee": null,
#         "deadline": null
#     },
#     {
#         "task": "Test Tamil demo videos",
#         "assignee": "Ravi",
#         "deadline": "Friday"
#     }
# ]

# timeline:

# [
#     {
#         "action": "Test Tamil demo videos",
#         "date": "Friday"
#     }
# ]

# The undated task MUST NOT appear in timeline.


# ============================================================
# 13. LANGUAGE
# ============================================================

# Understand:

# - English
# - Tamil
# - Tamil-English code-mixed speech
# - Indian English

# Do not treat Tamil and English as different speakers.


# ============================================================
# 14. OUTPUT
# ============================================================

# Return exactly these fields:

# title
# objective
# meeting_summary
# tasks_assigned
# decision_points
# objections
# action_items
# timeline

# Objective MUST:

# - be generated from transcript analysis
# - never be empty
# - never be null
# - never be a refusal
# - describe the actual purpose of the meeting

# Timeline MUST:

# - contain only actions with explicitly mentioned deadlines/dates
# - use the exact stated deadline/date
# - never contain invented dates
# - be an empty list if no deadline/date is mentioned

# Do not add additional fields.
# """


# # ============================================================
# # GENERATE MEETING INTELLIGENCE
# # ============================================================

# def generate_meeting_summary(transcript: str):

#     transcript = (
#         transcript or ""
#     ).strip()

#     # --------------------------------------------------------
#     # EMPTY TRANSCRIPT
#     # --------------------------------------------------------

#     if not transcript:

#         return {
#             "title": "Untitled Meeting",

#             "objective":
#                 "No meeting objective can be generated "
#                 "because no transcript was provided.",

#             "meeting_summary":
#                 "No transcript was available.",

#             "tasks_assigned": [],
#             "decision_points": [],
#             "objections": [],
#             "action_items": [],
#             "timeline": [],
#         }

#     # --------------------------------------------------------
#     # LOG
#     # --------------------------------------------------------

#     print()
#     print("=" * 70)
#     print("MEETMIND - LLAMA MEETING INTELLIGENCE")
#     print("=" * 70)

#     print(
#         "LLM Model:",
#         LLAMA_MODEL,
#     )

#     print(
#         "Speaker diarization:",
#         "DISABLED",
#     )

#     print(
#         "Transcript length:",
#         len(transcript),
#         "characters",
#     )

#     print(
#         "Analyzing COMPLETE transcript..."
#     )

#     print("=" * 70)

#     # --------------------------------------------------------
#     # USER PROMPT
#     # --------------------------------------------------------

#     user_content = f"""
# Analyze the COMPLETE meeting transcript below.

# Your output must be based ONLY on the transcript.

# IMPORTANT:

# The objective is mandatory.

# Do not wait for the speaker to explicitly say
# "objective".

# Infer the actual purpose of the meeting from the
# complete discussion.

# The meeting summary must be an executive-style summary
# that captures:

# - the main purpose
# - important discussion
# - current status
# - problems or gaps
# - decisions
# - next steps

# Do not simply copy the transcript.

# Do not invent information.

# IMPORTANT TIMELINE RULE:

# The Timeline must contain ONLY actions for which the
# meeting transcript explicitly mentions a date or deadline.

# If an action has no explicitly stated date/deadline,
# do NOT include it in the Timeline.

# Never infer or invent dates.

# MEETING TRANSCRIPT
# ==================

# {transcript}

# ==================

# Return the required structured meeting intelligence.
# """

#     messages = [
#         {
#             "role": "system",
#             "content": SYSTEM_PROMPT,
#         },
#         {
#             "role": "user",
#             "content": user_content,
#         },
#     ]

#     # --------------------------------------------------------
#     # LLAMA CALL
#     # --------------------------------------------------------

#     def _call_llama(chat_messages):

#         try:

#             response = chat(
#                 model=LLAMA_MODEL,
#                 messages=chat_messages,
#                 format=MeetingResult.model_json_schema(),
#                 options={
#                     "temperature": 0,
#                 },
#             )

#         except Exception as exc:

#             raise RuntimeError(
#                 "Could not connect to Ollama/Llama 3.1 8B. "
#                 f"Make sure '{LLAMA_MODEL}' is available. "
#                 f"Original error: {exc}"
#             ) from exc

#         content = (
#             response.message.content or ""
#         ).strip()

#         if not content:

#             raise RuntimeError(
#                 "Llama returned an empty response."
#             )

#         try:

#             result = (
#                 MeetingResult
#                 .model_validate_json(content)
#             )

#             return result, content

#         except Exception as exc:

#             print()
#             print("=" * 70)
#             print("INVALID LLAMA STRUCTURED OUTPUT")
#             print("=" * 70)
#             print(content)
#             print("=" * 70)

#             raise RuntimeError(
#                 "Llama returned invalid structured output: "
#                 f"{exc}"
#             ) from exc

#     # --------------------------------------------------------
#     # FIRST LLAMA CALL
#     # --------------------------------------------------------

#     meeting_result, raw_response = (
#         _call_llama(messages)
#     )

#     # --------------------------------------------------------
#     # OBJECTIVE RETRY
#     # --------------------------------------------------------

#     if _looks_like_refusal(
#         meeting_result.objective
#     ):

#         print()
#         print("=" * 70)
#         print(
#             "OBJECTIVE INVALID - RETRYING"
#         )
#         print("=" * 70)

#         retry_messages = messages + [
#             {
#                 "role": "assistant",
#                 "content": raw_response,
#             },
#             {
#                 "role": "user",
#                 "content": """
# Your previous objective was empty, a refusal, or a
# placeholder.

# Re-read the COMPLETE transcript.

# Generate ONE specific sentence explaining the actual
# purpose of the meeting.

# The purpose can be inferred from what was reviewed,
# discussed, tested, decided, or planned.

# Do not refuse.

# Do not say that the objective is unknown.

# Do not mention this instruction in the answer.
# """,
#             },
#         ]

#         meeting_result, raw_response = (
#             _call_llama(retry_messages)
#         )

#     # --------------------------------------------------------
#     # OBJECTIVE VALIDATION
#     # --------------------------------------------------------

#     objective = (
#         meeting_result.objective.strip()
#         if meeting_result.objective
#         else ""
#     )

#     if (
#         not objective
#         or _looks_like_refusal(objective)
#     ):

#         raise RuntimeError(
#             "Llama could not produce a valid meeting "
#             "objective after retry."
#         )

#     # --------------------------------------------------------
#     # TITLE
#     # --------------------------------------------------------

#     title = (
#         meeting_result.title.strip()
#         if meeting_result.title
#         else "Untitled Meeting"
#     )

#     # --------------------------------------------------------
#     # SUMMARY
#     # --------------------------------------------------------

#     meeting_summary = (
#         meeting_result.meeting_summary.strip()
#         if meeting_result.meeting_summary
#         else "No summary available."
#     )

#     # --------------------------------------------------------
#     # FINAL RESULT
#     # --------------------------------------------------------

#     result = {
#         "title": title,

#         "objective": objective,

#         "meeting_summary": meeting_summary,

#         "tasks_assigned": [],

#         "decision_points": [],

#         "objections": [],

#         "action_items": [],

#         "timeline": [],
#     }

#     # ========================================================
#     # TASKS
#     # ========================================================

#     for task in meeting_result.tasks_assigned:

#         if not task.task:
#             continue

#         task_text = task.task.strip()

#         if not task_text:
#             continue

#         item = {
#             "task": task_text
#         }

#         # ----------------------------------------------------
#         # ASSIGNEE
#         # ----------------------------------------------------

#         if task.assignee:

#             assignee = (
#                 task.assignee.strip()
#             )

#             if _looks_like_real_name(
#                 assignee
#             ):

#                 item["assignee"] = assignee

#         # ----------------------------------------------------
#         # DEADLINE
#         # ----------------------------------------------------

#         if task.deadline:

#             deadline = (
#                 task.deadline.strip()
#             )

#             if (
#                 deadline
#                 and
#                 deadline.lower()
#                 not in _PLACEHOLDER_VALUES
#             ):

#                 item["deadline"] = deadline

#         result[
#             "tasks_assigned"
#         ].append(item)

#     # ========================================================
#     # DECISIONS
#     # ========================================================

#     for decision in (
#         meeting_result.decision_points
#     ):

#         if not decision:
#             continue

#         decision = decision.strip()

#         if decision:

#             result[
#                 "decision_points"
#             ].append(decision)

#     # ========================================================
#     # OBJECTIONS
#     # ========================================================

#     for objection in (
#         meeting_result.objections
#     ):

#         if not objection:
#             continue

#         objection = objection.strip()

#         if objection:

#             result[
#                 "objections"
#             ].append(objection)

#     # ========================================================
#     # ACTION ITEMS
#     # ========================================================

#     for action in (
#         meeting_result.action_items
#     ):

#         if not action:
#             continue

#         action = action.strip()

#         if action:

#             result[
#                 "action_items"
#             ].append(action)

#     # ========================================================
#     # TIMELINE
#     # ========================================================

#     for timeline_item in (
#         meeting_result.timeline
#     ):

#         if not timeline_item:
#             continue

#         action = (
#             timeline_item.action or ""
#         ).strip()

#         date = (
#             timeline_item.date or ""
#         ).strip()

#         # ----------------------------------------------------
#         # STRICT VALIDATION
#         # ----------------------------------------------------
#         # Timeline requires BOTH:
#         #   1. an action
#         #   2. an explicitly supplied date/deadline
#         #
#         # Empty/placeholder dates are rejected.
#         # ----------------------------------------------------

#         if not action:
#             continue

#         if not date:
#             continue

#         if date.lower() in _PLACEHOLDER_VALUES:
#             continue

#         result[
#             "timeline"
#         ].append(
#             {
#                 "action": action,
#                 "date": date,
#             }
#         )

#     # ========================================================
#     # ADDITIONAL TIMELINE VALIDATION
#     # ========================================================
#     #
#     # Keep Timeline synchronized with actual task deadlines.
#     #
#     # This prevents Llama from accidentally creating a Timeline
#     # entry for something that is not present in tasks_assigned.
#     #
#     # An action is retained when:
#     #
#     # - it exactly matches a task, OR
#     # - it is clearly represented by a task with a deadline.
#     #
#     # ========================================================

#     validated_timeline = []

#     for timeline_item in result["timeline"]:

#         timeline_action = (
#             timeline_item["action"]
#             .strip()
#             .lower()
#         )

#         timeline_date = (
#             timeline_item["date"]
#             .strip()
#             .lower()
#         )

#         matched = False

#         for task_item in result["tasks_assigned"]:

#             task_text = (
#                 task_item["task"]
#                 .strip()
#                 .lower()
#             )

#             task_deadline = (
#                 task_item.get("deadline")
#                 or ""
#             ).strip().lower()

#             # Exact task/action match with deadline.
#             if (
#                 timeline_action == task_text
#                 and task_deadline
#                 and task_deadline == timeline_date
#             ):
#                 matched = True
#                 break

#             # Allow the model to phrase the timeline action
#             # slightly differently while still requiring the
#             # corresponding task to have a deadline.
#             if (
#                 task_deadline
#                 and task_deadline == timeline_date
#                 and (
#                     timeline_action in task_text
#                     or task_text in timeline_action
#                 )
#             ):
#                 matched = True
#                 break

#         if matched:
#             validated_timeline.append(
#                 timeline_item
#             )

#     result["timeline"] = validated_timeline

#     # ========================================================
#     # LOG RESULT
#     # ========================================================

#     print()
#     print("=" * 70)
#     print("MEETING INTELLIGENCE GENERATED")
#     print("=" * 70)

#     print()
#     print("TITLE:")
#     print(result["title"])

#     print()
#     print("OBJECTIVE:")
#     print(result["objective"])

#     print()
#     print("SUMMARY:")
#     print(result["meeting_summary"])

#     print()
#     print("TASKS:")

#     if result["tasks_assigned"]:

#         for task in result["tasks_assigned"]:

#             print(
#                 "-",
#                 task["task"]
#             )

#             if "assignee" in task:

#                 print(
#                     "  Assignee:",
#                     task["assignee"]
#                 )

#             if "deadline" in task:

#                 print(
#                     "  Deadline:",
#                     task["deadline"]
#                 )

#     else:

#         print(
#             "- No tasks identified."
#         )

#     print()
#     print("DECISIONS:")

#     if result["decision_points"]:

#         for decision in (
#             result["decision_points"]
#         ):

#             print(
#                 "-",
#                 decision
#             )

#     else:

#         print(
#             "- No decisions identified."
#         )

#     print()
#     print("OBJECTIONS:")

#     if result["objections"]:

#         for objection in (
#             result["objections"]
#         ):

#             print(
#                 "-",
#                 objection
#             )

#     else:

#         print("- None")

#     print()
#     print("ACTION ITEMS:")

#     if result["action_items"]:

#         for action in (
#             result["action_items"]
#         ):

#             print(
#                 "-",
#                 action
#             )

#     else:

#         print(
#             "- No action items identified."
#         )

#     # ========================================================
#     # TIMELINE
#     # ========================================================

#     print()
#     print("TIMELINE:")

#     if result["timeline"]:

#         print(
#             f"{'S.No':<8}"
#             f"{'Action':<50}"
#             f"Date"
#         )

#         print("-" * 80)

#         for index, item in enumerate(
#             result["timeline"],
#             start=1
#         ):

#             print(
#                 f"{index:<8}"
#                 f"{item['action']:<50}"
#                 f"{item['date']}"
#             )

#     else:

#         print(
#             "- No actions with explicit deadlines identified."
#         )

#     print()
#     print("=" * 70)

#     return result







# old code below ###############################################

import os
import re

from typing import Optional

from ollama import chat

from pydantic import BaseModel


# ============================================================
# CONFIGURATION
# ============================================================

LLAMA_MODEL = os.getenv(
    "MEETMIND_LLAMA_MODEL",
    "llama3.1:8b",
)


# ============================================================
# PLACEHOLDER / REFUSAL DETECTION
# ============================================================

_PLACEHOLDER_VALUES = {
    "unknown",
    "not mentioned",
    "not specified",
    "n/a",
    "none",
    "null",
    "",
}


_REFUSAL_PATTERNS = (
    "could not be generated",
    "could not be determined",
    "cannot be determined",
    "unable to determine",
    "no objective",
    "no objective found",
    "not mentioned",
    "not specified",
    "unknown",
)


def _looks_like_refusal(text: str) -> bool:
    text = (text or "").strip().lower()

    if not text:
        return True

    return any(
        pattern in text
        for pattern in _REFUSAL_PATTERNS
    )


# ============================================================
# NAME VALIDATION
# ============================================================

_PRONOUN_STARTS = (
    "i ",
    "i'll",
    "i will",
    "i'm",
    "we ",
    "we'll",
    "we will",
    "we're",
    "you ",
    "you'll",
    "they ",
    "he ",
    "she ",
    "it ",
)


_TASK_VERB_PATTERN = re.compile(
    r"\b("
    r"will|test|check|review|update|send|do|complete|"
    r"finish|verify|fix|build|create|write|prepare|"
    r"evaluate|develop|integrate|implement|analyze|analyse"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_real_name(value: str) -> bool:
    value = (value or "").strip()

    if not value:
        return False

    lowered = value.lower()

    if lowered in _PLACEHOLDER_VALUES:
        return False

    if lowered.startswith(_PRONOUN_STARTS):
        return False

    # A person's name should not be an entire sentence.
    if len(value.split()) > 3:
        return False

    # Prevent task fragments such as:
    # "I'll test"
    # "will evaluate"
    if _TASK_VERB_PATTERN.search(lowered):
        return False

    return True


# ============================================================
# PYDANTIC OUTPUT SCHEMA
# ============================================================

class Task(BaseModel):
    task: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None


class TimelineItem(BaseModel):
    action: str
    date: str


class MeetingResult(BaseModel):
    title: str
    objective: str
    meeting_summary: str
    tasks_assigned: list[Task]
    decision_points: list[str]
    objections: list[str]
    action_items: list[str]
    timeline: list[TimelineItem]


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are MeetMind, an AI meeting intelligence system.

Your job is to analyze the COMPLETE meeting transcript and
produce accurate, useful, professional meeting intelligence.

The transcript may contain:

- English
- Tamil
- Tamil-English code-mixed speech
- Indian English
- informal spoken language
- automatic speech recognition errors

Speaker diarization is DISABLED.

Do not create speaker labels.


============================================================
STRICT TRANSCRIPT GROUNDING
============================================================

Use ONLY information supported by the transcript.

Never invent:

- names
- people
- tasks
- assignees
- deadlines
- dates
- decisions
- objections
- action items
- facts

You may correct an obvious ASR error only when the intended
meaning is clear from the surrounding context.


============================================================
1. TITLE
============================================================

Generate a short, meaningful title based on the actual meeting.

The title should describe the main subject of the meeting.

Avoid generic titles such as:

"Meeting"

"Project Meeting"

"Discussion"

when a more specific title can be generated.


============================================================
2. OBJECTIVE
============================================================

The objective is MANDATORY.

Analyze the COMPLETE transcript and determine WHY the meeting
was held.

The speaker does not need to explicitly say:

"The objective is..."

Infer the purpose from:

- what is being reviewed
- what is being tested
- what problem is being addressed
- what the participants are trying to accomplish
- what outcome the meeting is working toward

Example:

Transcript:

"Today we are testing the Parrotlet speech recognition system.

We want to verify whether the complete recording is transcribed
correctly."

Objective:

"Verify the accuracy and completeness of the Parrotlet
transcription system."

The objective must:

- be specific
- be concise
- explain why the meeting happened
- be based on the complete transcript
- be generated through analysis

NEVER return:

"Objective could not be determined."

"No objective found."

"No objective could be generated."

"Not mentioned."

"Unknown."

Even when the objective is not explicitly stated, infer the
most reasonable purpose from the complete discussion.


============================================================
3. MEETING SUMMARY
============================================================

Generate a PROFESSIONAL EXECUTIVE-STYLE SUMMARY.

Do NOT simply shorten or copy the transcript.

The summary must explain:

1. What the meeting was primarily about.
2. The important topics discussed.
3. The current status or progress.
4. Problems, concerns, limitations, or gaps.
5. Important decisions.
6. Planned next steps.

The summary should allow someone who did NOT attend the meeting
to understand what happened.

When applicable, clearly distinguish:

- CURRENT STATUS
- KEY DISCUSSION
- PROBLEMS / GAPS
- DECISIONS
- NEXT STEPS

Do not invent information.

Preserve important technical terminology.

For a normal meeting, produce approximately 3-6 sentences.

For a short meeting, use fewer sentences.

For a long meeting, provide enough detail to cover the major
outcomes without becoming repetitive.

The summary should read like a professional meeting report,
not like a transcript.


============================================================
4. TASKS
============================================================

Extract only genuine work that needs to be completed.

Do not convert every statement into a task.

Example:

"We discussed database integration."

This is discussion, not necessarily a task.

Example:

"We need to integrate the backend database."

This is a task.

Tasks must represent actual work.


============================================================
5. TASK ASSIGNEE
============================================================

Only provide an assignee when a person's NAME is explicitly
identified as responsible for the task.

Example:

"Ravi will evaluate the transcription quality."

Correct:

task:

"Evaluate the transcription quality"

assignee:

"Ravi"

If the transcript says:

"I will evaluate the transcription quality."

DO NOT use:

"I"

"I'll"

"I'll test"

"will evaluate"

as the assignee.

In that case:

assignee = null

The assignee field is ONLY for a person's name.


============================================================
6. DEADLINE
============================================================

Only provide a deadline when the transcript explicitly states
a deadline or date for the task.

Examples:

"I will complete this by Friday."

deadline = "Friday"

"We will finish it next week."

deadline = "next week"

"Let's test the recordings on September 5."

deadline = "September 5"

"The demo needs to be ready tomorrow."

deadline = "tomorrow"

If no deadline or date is explicitly stated:

deadline = null

Never infer or invent a deadline.

Do NOT convert general future language such as:

- "later"
- "soon"
- "in the future"
- "after this"
- "next step"

into a deadline unless the transcript gives a specific
time/date reference.


============================================================
7. TIMELINE
============================================================

The Timeline is a separate section containing ONLY actions
that have an explicitly mentioned deadline or date in the
meeting transcript.

Timeline format:

| S.No | Action | Date |

Rules:

1. Include ONLY actions with an explicitly mentioned deadline
   or date.

2. The action must correspond to an actual task/action discussed
   in the transcript.

3. Use the explicitly stated date/deadline.

4. Do NOT invent dates.

5. Do NOT infer dates from context.

6. Do NOT include tasks without a deadline.

7. Do NOT include general discussion points.

8. Do NOT include decisions unless they also represent an
   explicit action with a stated deadline.

Example:

Transcript:

"Ravi will test the Tamil demo videos by Friday."

Timeline:

action:

"Test the Tamil demo videos"

date:

"Friday"

Example:

Transcript:

"We need to test additional recordings."

There is no date.

Therefore:

timeline = []

Example:

Transcript:

"We need to test additional recordings by September 5."

Timeline:

action:

"Test additional recordings"

date:

"September 5"

If no action with a specific deadline/date is mentioned:

timeline = []


============================================================
8. DECISIONS
============================================================

Extract only decisions that were actually made.

Example:

"We decided to continue testing both Tamil and English audio."

This is a decision.

Example:

"We discussed testing Tamil and English audio."

This is discussion, not necessarily a decision.

If there are no actual decisions:

return []


============================================================
9. OBJECTIONS / CONCERNS
============================================================

Extract genuine:

- objections
- disagreements
- concerns
- reservations
- blockers
- explicitly raised risks

Example:

"I'm concerned that longer recordings may cause memory problems."

This is a concern.

Do not invent objections simply because a problem was discussed.

If no genuine objection or concern exists:

return []


============================================================
10. ACTION ITEMS
============================================================

Extract explicit follow-up actions resulting from the meeting.

Example:

"The action item is to test longer audio and verify the results."

Return:

"Test longer audio and verify the results"

Do not invent action items.

If none exist:

return []


============================================================
11. TASKS VS ACTION ITEMS
============================================================

Avoid unnecessary duplication.

TASK:

Work that needs to be completed.

ACTION ITEM:

An explicit follow-up action resulting from the meeting.

Use judgment when the same statement could fit both categories.


============================================================
12. TIMELINE VS DEADLINE
============================================================

The task object may contain a deadline.

The Timeline is a separate presentation of ONLY those tasks
that have an explicitly stated deadline/date.

For example:

tasks_assigned:

[
    {
        "task": "Test additional recordings",
        "assignee": null,
        "deadline": null
    },
    {
        "task": "Test Tamil demo videos",
        "assignee": "Ravi",
        "deadline": "Friday"
    }
]

timeline:

[
    {
        "action": "Test Tamil demo videos",
        "date": "Friday"
    }
]

The undated task MUST NOT appear in timeline.


============================================================
13. LANGUAGE
============================================================

Understand:

- English
- Tamil
- Tamil-English code-mixed speech
- Indian English

Do not treat Tamil and English as different speakers.


============================================================
14. OUTPUT
============================================================

Return exactly these fields:

title

objective

meeting_summary

tasks_assigned

decision_points

objections

action_items

timeline

Objective MUST:

- be generated from transcript analysis
- never be empty
- never be null
- never be a refusal
- describe the actual purpose of the meeting

Timeline MUST:

- contain only actions with explicitly mentioned deadlines/dates
- use the exact stated deadline/date
- never contain invented dates
- be an empty list if no deadline/date is mentioned

Do not add additional fields.

"""


# ============================================================
# GENERATE MEETING INTELLIGENCE
# ============================================================

def generate_meeting_summary(transcript: str):
    transcript = (
        transcript or ""
    ).strip()

    # --------------------------------------------------------
    # EMPTY TRANSCRIPT
    # --------------------------------------------------------

    if not transcript:
        return {
            "title": "Untitled Meeting",
            "objective": (
                "No meeting objective can be generated "
                "because no transcript was provided."
            ),
            "meeting_summary": (
                "No transcript was available."
            ),
            "tasks_assigned": [],
            "decision_points": [],
            "objections": [],
            "action_items": [],
            "timeline": [],
        }

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("MEETMIND - LLAMA MEETING INTELLIGENCE")
    print("=" * 70)

    print(
        "LLM Model:",
        LLAMA_MODEL,
    )

    print(
        "Speaker diarization:",
        "DISABLED",
    )

    print(
        "Transcript length:",
        len(transcript),
        "characters",
    )

    print(
        "Analyzing COMPLETE transcript..."
    )

    print("=" * 70)

    # --------------------------------------------------------
    # USER PROMPT
    # --------------------------------------------------------

    user_content = f"""
Analyze the COMPLETE meeting transcript below.

Your output must be based ONLY on the transcript.

IMPORTANT:

The objective is mandatory.

Do not wait for the speaker to explicitly say
"objective".

Infer the actual purpose of the meeting from the
complete discussion.

The meeting summary must be an executive-style summary
that captures:

- the main purpose
- important discussion
- current status
- problems or gaps
- decisions
- next steps

Do not simply copy the transcript.

Do not invent information.

IMPORTANT TIMELINE RULE:

The Timeline must contain ONLY actions for which the
meeting transcript explicitly mentions a date or deadline.

If an action has no explicitly stated date/deadline,
do NOT include it in the Timeline.

Never infer or invent dates.

MEETING TRANSCRIPT

==================

{transcript}

==================

Return the required structured meeting intelligence.
"""

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

    # --------------------------------------------------------
    # LLAMA CALL
    # --------------------------------------------------------

    def _call_llama(chat_messages):
        try:
            response = chat(
                model=LLAMA_MODEL,
                messages=chat_messages,
                format=MeetingResult.model_json_schema(),
                options={
                    "temperature": 0,
                },
            )

        except Exception as exc:
            raise RuntimeError(
                "Could not connect to Ollama/Llama 3.1 8B. "
                f"Make sure '{LLAMA_MODEL}' is available. "
                f"Original error: {exc}"
            ) from exc

        content = (
            response.message.content or ""
        ).strip()

        if not content:
            raise RuntimeError(
                "Llama returned an empty response."
            )

        try:
            result = (
                MeetingResult
                .model_validate_json(content)
            )

            return result, content

        except Exception as exc:
            print()
            print("=" * 70)
            print("INVALID LLAMA STRUCTURED OUTPUT")
            print("=" * 70)
            print(content)
            print("=" * 70)

            raise RuntimeError(
                "Llama returned invalid structured output: "
                f"{exc}"
            ) from exc

    # --------------------------------------------------------
    # FIRST LLAMA CALL
    # --------------------------------------------------------

    meeting_result, raw_response = (
        _call_llama(messages)
    )

    # --------------------------------------------------------
    # OBJECTIVE RETRY
    # --------------------------------------------------------

    if _looks_like_refusal(
        meeting_result.objective
    ):
        print()
        print("=" * 70)
        print(
            "OBJECTIVE INVALID - RETRYING"
        )
        print("=" * 70)

        retry_messages = messages + [
            {
                "role": "assistant",
                "content": raw_response,
            },
            {
                "role": "user",
                "content": """
Your previous objective was empty, a refusal, or a
placeholder.

Re-read the COMPLETE transcript.

Generate ONE specific sentence explaining the actual
purpose of the meeting.

The purpose can be inferred from what was reviewed,
discussed, tested, decided, or planned.

Do not refuse.

Do not say that the objective is unknown.

Do not mention this instruction in the answer.
""",
            },
        ]

        meeting_result, raw_response = (
            _call_llama(retry_messages)
        )

    # --------------------------------------------------------
    # OBJECTIVE VALIDATION
    # --------------------------------------------------------

    objective = (
        meeting_result.objective.strip()
        if meeting_result.objective
        else ""
    )

    if (
        not objective
        or _looks_like_refusal(objective)
    ):
        raise RuntimeError(
            "Llama could not produce a valid meeting "
            "objective after retry."
        )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = (
        meeting_result.title.strip()
        if meeting_result.title
        else "Untitled Meeting"
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    meeting_summary = (
        meeting_result.meeting_summary.strip()
        if meeting_result.meeting_summary
        else "No summary available."
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    result = {
        "title": title,
        "objective": objective,
        "meeting_summary": meeting_summary,
        "tasks_assigned": [],
        "decision_points": [],
        "objections": [],
        "action_items": [],
        "timeline": [],
    }

    # ========================================================
    # TASKS
    # ========================================================

    for task in meeting_result.tasks_assigned:

        if not task.task:
            continue

        task_text = task.task.strip()

        if not task_text:
            continue

        item = {
            "task": task_text
        }

        # ----------------------------------------------------
        # ASSIGNEE
        # ----------------------------------------------------

        if task.assignee:
            assignee = (
                task.assignee.strip()
            )

            if _looks_like_real_name(
                assignee
            ):
                item["assignee"] = assignee

        # ----------------------------------------------------
        # DEADLINE
        # ----------------------------------------------------

        if task.deadline:
            deadline = (
                task.deadline.strip()
            )

            if (
                deadline
                and deadline.lower()
                not in _PLACEHOLDER_VALUES
            ):
                item["deadline"] = deadline

        result[
            "tasks_assigned"
        ].append(item)

    # ========================================================
    # DECISIONS
    # ========================================================

    for decision in (
        meeting_result.decision_points
    ):

        if not decision:
            continue

        decision = decision.strip()

        if decision:
            result[
                "decision_points"
            ].append(decision)

    # ========================================================
    # OBJECTIONS
    # ========================================================

    for objection in (
        meeting_result.objections
    ):

        if not objection:
            continue

        objection = objection.strip()

        if objection:
            result[
                "objections"
            ].append(objection)

    # ========================================================
    # ACTION ITEMS
    # ========================================================

    for action in (
        meeting_result.action_items
    ):

        if not action:
            continue

        action = action.strip()

        if action:
            result[
                "action_items"
            ].append(action)

    # ========================================================
    # TIMELINE
    # ========================================================

    for timeline_item in (
        meeting_result.timeline
    ):

        if not timeline_item:
            continue

        action = (
            timeline_item.action or ""
        ).strip()

        date = (
            timeline_item.date or ""
        ).strip()

        # ----------------------------------------------------
        # STRICT VALIDATION
        # ----------------------------------------------------

        # Timeline requires BOTH:
        #
        # 1. an action
        # 2. an explicitly supplied date/deadline
        #
        # Empty/placeholder dates are rejected.

        if not action:
            continue

        if not date:
            continue

        if date.lower() in _PLACEHOLDER_VALUES:
            continue

        result[
            "timeline"
        ].append(
            {
                "action": action,
                "date": date,
            }
        )

    # ========================================================
    # ADDITIONAL TIMELINE VALIDATION
    # ========================================================

    # Keep Timeline synchronized with actual task deadlines.
    #
    # This prevents Llama from accidentally creating a Timeline
    # entry for something that is not present in tasks_assigned.
    #
    # An action is retained when:
    #
    # - it exactly matches a task, OR
    # - it is clearly represented by a task with a deadline.

    # ========================================================

    validated_timeline = []

    for timeline_item in result["timeline"]:

        timeline_action = (
            timeline_item["action"]
            .strip()
            .lower()
        )

        timeline_date = (
            timeline_item["date"]
            .strip()
            .lower()
        )

        matched = False

        for task_item in result["tasks_assigned"]:

            task_text = (
                task_item["task"]
                .strip()
                .lower()
            )

            task_deadline = (
                task_item.get("deadline")
                or ""
            ).strip().lower()

            # Exact task/action match with deadline.
            if (
                timeline_action == task_text
                and task_deadline
                and task_deadline == timeline_date
            ):
                matched = True
                break

            # Allow the model to phrase the timeline action
            # slightly differently while still requiring the
            # corresponding task to have a deadline.
            if (
                task_deadline
                and task_deadline == timeline_date
                and (
                    timeline_action in task_text
                    or task_text in timeline_action
                )
            ):
                matched = True
                break

        if matched:
            validated_timeline.append(
                timeline_item
            )

    result["timeline"] = validated_timeline

    # ========================================================
    # LOG RESULT
    # ========================================================

    print()
    print("=" * 70)
    print("MEETING INTELLIGENCE GENERATED")
    print("=" * 70)

    print()
    print("TITLE:")
    print(result["title"])

    print()
    print("OBJECTIVE:")
    print(result["objective"])

    print()
    print("SUMMARY:")
    print(result["meeting_summary"])

    print()
    print("TASKS:")

    if result["tasks_assigned"]:

        for task in result["tasks_assigned"]:

            print(
                "-",
                task["task"]
            )

            if "assignee" in task:
                print(
                    "  Assignee:",
                    task["assignee"]
                )

            if "deadline" in task:
                print(
                    "  Deadline:",
                    task["deadline"]
                )

    else:
        print(
            "- No tasks identified."
        )

    print()
    print("DECISIONS:")

    if result["decision_points"]:

        for decision in (
            result["decision_points"]
        ):

            print(
                "-",
                decision
            )

    else:
        print(
            "- No decisions identified."
        )

    print()
    print("OBJECTIONS:")

    if result["objections"]:

        for objection in (
            result["objections"]
        ):

            print(
                "-",
                objection
            )

    else:
        print("- None")

    print()
    print("ACTION ITEMS:")

    if result["action_items"]:

        for action in (
            result["action_items"]
        ):

            print(
                "-",
                action
            )

    else:
        print(
            "- No action items identified."
        )

    # ========================================================
    # TIMELINE
    # ========================================================

    print()
    print("TIMELINE:")

    if result["timeline"]:

        print(
            f"{'S.No':<8}"
            f"{'Action':<50}"
            f"Date"
        )

        print("-" * 80)

        for index, item in enumerate(
            result["timeline"],
            start=1
        ):

            print(
                f"{index:<8}"
                f"{item['action']:<50}"
                f"{item['date']}"
            )

    else:
        print(
            "- No actions with explicit deadlines identified."
        )

    print()
    print("=" * 70)

    return result