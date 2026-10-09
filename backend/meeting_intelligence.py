# """
# MeetMind - Meeting Intelligence
# Mistral 128B API and Qwen3-27B API
# Meeting summary, action items, timeline, and hierarchical mindmap.
# """

# import json
# import os
# import re
# from typing import Optional

# import requests
# from pydantic import BaseModel, Field

# from mistral_client import call_mistral, MISTRAL_MODEL as DEFAULT_MISTRAL_MODEL


# # ============================================================
# # CONFIGURATION
# # ============================================================

# MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)

# QWEN_API_URL = os.getenv(
#     "QWEN_API_URL",
#     "http://115.112.206.245/api/chat/completions",
# )
# QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
# QWEN_MODEL = os.getenv("QWEN_MODEL", "ai-switch.qwen3-27b")

# JSON_ONLY_INSTRUCTION = """
# Return exactly one valid JSON object.
# Do not include your thinking process, reasoning, introduction,
# Markdown fences, or explanatory text before or after the JSON.
# Use double quotes for JSON keys and strings.
# Do not use trailing commas.
# """


# # ============================================================
# # PYDANTIC SCHEMAS
# # ============================================================

# class Task(BaseModel):
#     task: str
#     assignee: Optional[str] = None
#     deadline: Optional[str] = None


# class TimelineItem(BaseModel):
#     action: str
#     date: str


# class MindMapNode(BaseModel):
#     title: str
#     children: list["MindMapNode"] = Field(default_factory=list)


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
# # QWEN3-27B CLOUD API
# # ============================================================

# def _call_qwen(
#     *,
#     system_prompt: str,
#     user_prompt: str,
#     temperature: float = 0.0,
#     max_tokens: int = 4096,
# ) -> str:
#     """Call the configured Qwen3-27B API."""

#     if not QWEN_API_URL:
#         raise RuntimeError("QWEN_API_URL is not configured.")

#     if not QWEN_API_KEY:
#         raise RuntimeError("QWEN_API_KEY is not configured.")

#     headers = {
#         "Authorization": f"Bearer {QWEN_API_KEY}",
#         "Content-Type": "application/json",
#     }

#     payload = {
#         "model": QWEN_MODEL,
#         "messages": [
#             {
#                 "role": "system",
#                 "content": system_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
#             },
#             {
#                 "role": "user",
#                 "content": user_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
#             },
#         ],
#         "temperature": temperature,
#         "max_tokens": max_tokens,
#     }

#     try:
#         response = requests.post(
#             QWEN_API_URL,
#             headers=headers,
#             json=payload,
#             timeout=300,
#         )
#         response.raise_for_status()
#         data = response.json()

#     except requests.RequestException as exc:
#         raise RuntimeError(
#             f"Qwen API request failed: {exc}"
#         ) from exc

#     except ValueError as exc:
#         raise RuntimeError(
#             "Qwen API returned an invalid HTTP JSON response."
#         ) from exc

#     try:
#         content = data["choices"][0]["message"]["content"]
#     except (KeyError, IndexError, TypeError) as exc:
#         raise RuntimeError(
#             f"Unexpected Qwen API response structure: {data}"
#         ) from exc

#     if not isinstance(content, str) or not content.strip():
#         raise RuntimeError("Qwen API returned an empty response.")

#     return content.strip()


# # ============================================================
# # ROBUST JSON EXTRACTION
# # ============================================================

# def _remove_thinking_content(text: str) -> str:
#     """Remove common reasoning sections and surrounding Markdown."""

#     text = re.sub(
#         r"<think\b[^>]*>.*?</think\s*>",
#         "",
#         text,
#         flags=re.IGNORECASE | re.DOTALL,
#     )

#     text = re.sub(
#         r"<think\b[^>]*>.*$",
#         "",
#         text,
#         flags=re.IGNORECASE | re.DOTALL,
#     )

#     text = re.sub(
#         r"```(?:json|JSON)?[ \t]*",
#         "",
#         text,
#     )

#     text = text.replace("```", "")

#     return text.strip()


# def _extract_json_object(text: str, required_keys=None) -> str:
#     """
#     Extract one complete valid JSON object from an LLM response.

#     The scanner respects quoted strings and escaped characters,
#     so braces inside JSON strings do not break object detection.
#     """

#     if not isinstance(text, str) or not text.strip():
#         raise ValueError("The model returned an empty response.")

#     text = _remove_thinking_content(text)

#     candidates = []
#     length = len(text)

#     for start, char in enumerate(text):
#         if char != "{":
#             continue

#         depth = 0
#         in_string = False
#         escaped = False

#         for end in range(start, length):
#             current = text[end]

#             if in_string:
#                 if escaped:
#                     escaped = False
#                 elif current == "\\":
#                     escaped = True
#                 elif current == '"':
#                     in_string = False
#                 continue

#             if current == '"':
#                 in_string = True
#             elif current == "{":
#                 depth += 1
#             elif current == "}":
#                 depth -= 1

#                 if depth == 0:
#                     candidate = text[start:end + 1]

#                     try:
#                         parsed = json.loads(candidate)
#                     except json.JSONDecodeError:
#                         break

#                     if isinstance(parsed, dict):
#                         matching = (
#                             required_keys is None
#                             or required_keys.issubset(parsed.keys())
#                         )

#                         candidates.append(
#                             (
#                                 matching,
#                                 len(candidate),
#                                 start,
#                                 candidate,
#                             )
#                         )

#                     break

#     if not candidates:
#         raise ValueError(
#             "No complete valid JSON object was found in the model response."
#         )

#     if required_keys:
#         matching_candidates = [
#             candidate
#             for candidate in candidates
#             if candidate[0]
#         ]

#         if matching_candidates:
#             candidates = matching_candidates

#     # Prefer the largest object matching the expected schema.
#     # This helps avoid selecting a nested child object.
#     selected = max(
#         candidates,
#         key=lambda candidate: (
#             candidate[0],
#             candidate[1],
#             candidate[2],
#         ),
#     )

#     return selected[3]


# def _parse_mindmap_json(text: str) -> dict:
#     """Parse and validate the root of a mindmap JSON object."""

#     cleaned = _extract_json_object(
#         text,
#         required_keys={"title", "children"},
#     )

#     parsed = json.loads(cleaned)

#     if not isinstance(parsed, dict):
#         raise ValueError("Mindmap root must be a JSON object.")

#     if not isinstance(parsed.get("title"), str):
#         raise ValueError("Mindmap root must contain a title string.")

#     if not parsed["title"].strip():
#         raise ValueError("Mindmap root title cannot be empty.")

#     if not isinstance(parsed.get("children"), list):
#         raise ValueError("Mindmap children must be a list.")

#     return parsed


# # ============================================================
# # MEETING INTELLIGENCE PROMPT
# # ============================================================

# SYSTEM_PROMPT = """
# You are MeetMind, an AI meeting intelligence system.

# Analyze the complete meeting transcript and return accurate,
# professional meeting intelligence grounded in the transcript.

# The transcript may contain English, Tamil, Tamil-English code-mixed
# speech, Indian English, informal speech, and ASR errors.

# Speaker diarization is disabled. Do not create speaker labels.

# STRICT GROUNDING:
# - Never invent names, tasks, assignees, deadlines, dates,
#   decisions, objections, action items, or facts.
# - Correct an ASR error only when the intended meaning is clear.
# - Preserve important technical terminology.

# TITLE:
# Generate a short, meaningful title describing the actual meeting.

# OBJECTIVE:
# The objective is mandatory. Infer why the meeting was held from
# the complete discussion. Never return an empty objective or a
# generic refusal such as "Unknown" or "Not mentioned".

# SUMMARY:
# Write a professional executive-style summary, normally 3-6
# sentences. Cover the main subject, important topics, current
# status, problems, decisions, and next steps when present.
# Do not merely copy the transcript.

# TASKS:
# Extract genuine work that needs to be completed.
# Only assign a task to a named person explicitly identified
# as responsible. Do not use pronouns such as "I" or "we"
# as assignees. Use null if the responsible person's name
# is not explicitly stated.

# DEADLINES:
# Only use explicitly stated deadlines or dates.
# Never invent dates or infer a deadline from vague wording.

# TIMELINE:
# Include only actual actions with explicitly stated deadlines
# or dates. Use an empty list if no such actions exist.

# DECISIONS:
# Include only decisions that were actually made.

# OBJECTIONS:
# Include genuine objections, disagreements, concerns, blockers,
# or explicitly raised risks. Do not invent concerns.

# ACTION ITEMS:
# Include explicit follow-up actions. Do not invent actions.

# Return exactly these fields:
# title, objective, meeting_summary, tasks_assigned,
# decision_points, objections, action_items, timeline.

# The output must be a single valid JSON object.
# """


# # ============================================================
# # MEETING SUMMARY GENERATION
# # ============================================================

# def generate_meeting_summary(
#     transcript: str,
#     _llm_call=call_mistral,
#     _llm_model=MISTRAL_MODEL,
# ):
#     """Generate meeting intelligence using the selected LLM."""

#     transcript = (transcript or "").strip()

#     if not transcript:
#         raise ValueError("Cannot generate a summary from an empty transcript.")

#     user_prompt = f"""
# Analyze the COMPLETE meeting transcript.

# Return a JSON object containing exactly these fields:

# {{
#   "title": "Meeting title",
#   "objective": "Purpose of the meeting",
#   "meeting_summary": "Professional meeting summary",
#   "tasks_assigned": [
#     {{
#       "task": "Task description",
#       "assignee": null,
#       "deadline": null
#     }}
#   ],
#   "decision_points": [],
#   "objections": [],
#   "action_items": [],
#   "timeline": [
#     {{
#       "action": "Action with an explicit deadline",
#       "date": "Explicit deadline or date"
#     }}
#   ]
# }}

# Use empty lists when no relevant items exist.
# Use null for unknown task assignees and deadlines.
# Do not invent information.

# COMPLETE MEETING TRANSCRIPT:
# ============================
# {transcript}
# ============================

# Return only the JSON object.
# """

#     try:
#         content = _llm_call(
#             system_prompt=SYSTEM_PROMPT,
#             user_prompt=user_prompt,
#             temperature=0.0,
#             max_tokens=4096,
#         )

#     except Exception as exc:
#         raise RuntimeError(
#             f"Meeting summary generation failed for {_llm_model}: {exc}"
#         ) from exc

#     if not isinstance(content, str) or not content.strip():
#         raise RuntimeError(
#             f"{_llm_model} returned an empty meeting summary."
#         )

#     try:
#         cleaned = _extract_json_object(
#             content,
#             required_keys={
#                 "title",
#                 "objective",
#                 "meeting_summary",
#                 "tasks_assigned",
#                 "decision_points",
#                 "objections",
#                 "action_items",
#                 "timeline",
#             },
#         )

#         data = json.loads(cleaned)

#         result = MeetingResult.model_validate(data)

#     except Exception as exc:
#         raise RuntimeError(
#             f"{_llm_model} returned invalid structured meeting output: {exc}"
#         ) from exc

#     if not result.objective.strip():
#         raise RuntimeError(
#             f"{_llm_model} returned an empty meeting objective."
#         )

#     return result.model_dump()


# # ============================================================
# # MINDMAP VALIDATION
# # ============================================================

# def _clean_mindmap_node(node: dict) -> dict:
#     """Recursively validate and normalize mindmap nodes."""

#     if not isinstance(node, dict):
#         raise ValueError("Every mindmap node must be an object.")

#     title = node.get("title")

#     if not isinstance(title, str) or not title.strip():
#         raise ValueError("Every mindmap node must have a non-empty title.")

#     children = node.get("children", [])

#     if not isinstance(children, list):
#         raise ValueError(
#             f"Children for node {title!r} must be a list."
#         )

#     cleaned = {
#         "title": title.strip(),
#         "children": [
#             _clean_mindmap_node(child)
#             for child in children
#         ],
#     }

#     return cleaned


# # ============================================================
# # MINDMAP GENERATION
# # ============================================================

# MINDMAP_SYSTEM_PROMPT = """
# You are MeetMind, a meeting mindmap generator.

# Generate a hierarchical mindmap directly from the complete transcript.
# Do not generate the mindmap from a summary.

# Use only information supported by the transcript.
# Do not invent names, decisions, tasks, deadlines, or facts.
# Keep node titles concise and meaningful.

# Every node must contain:
# - title: a string
# - children: an array of child nodes, which may be empty

# Return exactly one JSON object with a root title and children.
# Do not add any other fields.
# Do not return reasoning, Markdown, introductions, or explanations.
# """


# def generate_mindmap(
#     transcript: str,
#     _llm_call=call_mistral,
#     _llm_model=MISTRAL_MODEL,
# ):
#     """Generate a hierarchical mindmap directly from the transcript."""

#     transcript = (transcript or "").strip()

#     if not transcript:
#         raise ValueError(
#             "Cannot generate a mindmap because the transcript is empty."
#         )

#     user_prompt = f"""
# Analyze the complete meeting transcript and create a hierarchical mindmap.

# Capture relevant:
# - Main topics
# - Technical discussions
# - Current status
# - Problems or challenges
# - Decisions
# - Action items
# - Tasks
# - Explicit timelines
# - Next steps

# Only include categories supported by the transcript.

# Return exactly this structure:

# {{
#   "title": "Main Meeting Topic",
#   "children": [
#     {{
#       "title": "Major Topic",
#       "children": [
#         {{
#           "title": "Important Detail",
#           "children": []
#         }}
#       ]
#     }}
#   ]
# }}

# Every node must contain a title and a children array.
# Do not include fields other than title and children.

# COMPLETE MEETING TRANSCRIPT:
# ============================
# {transcript}
# ============================

# Return only one valid JSON object.
# """

#     try:
#         content = _llm_call(
#             system_prompt=MINDMAP_SYSTEM_PROMPT,
#             user_prompt=user_prompt,
#             temperature=0.0,
#             max_tokens=4096,
#         )

#     except Exception as exc:
#         raise RuntimeError(
#             f"Mindmap generation failed for {_llm_model}: {exc}"
#         ) from exc

#     if not isinstance(content, str) or not content.strip():
#         raise RuntimeError(
#             f"{_llm_model} returned an empty mindmap response."
#         )

#     try:
#         mindmap_data = _parse_mindmap_json(content)

#     except Exception as first_error:
#         repair_prompt = f"""
# Repair the following malformed mindmap response.

# Requirements:
# - Preserve the existing information.
# - Do not invent new content.
# - Return one valid JSON object.
# - The root must contain title and children.
# - Every node must contain title and children.
# - Use only title and children fields.
# - Do not include reasoning, Markdown, or explanations.

# Malformed response:
# {content}

# Return only the repaired JSON object.
# """

#         try:
#             repaired_content = _llm_call(
#                 system_prompt=(
#                     "You are a JSON repair engine. Return only one valid "
#                     "mindmap JSON object. Do not explain anything."
#                 ),
#                 user_prompt=repair_prompt,
#                 temperature=0.0,
#                 max_tokens=4096,
#             )

#             mindmap_data = _parse_mindmap_json(repaired_content)

#         except Exception as repair_error:
#             raise RuntimeError(
#                 f"{_llm_model} returned invalid mindmap JSON, and "
#                 f"automatic repair failed. Original error: {first_error}. "
#                 f"Repair error: {repair_error}"
#             ) from repair_error

#     try:
#         return _clean_mindmap_node(mindmap_data)

#     except Exception as exc:
#         raise RuntimeError(
#             f"{_llm_model} returned an invalid mindmap structure: {exc}"
#         ) from exc


# # ============================================================
# # QWEN3-27B WRAPPERS
# # ============================================================

# def generate_meeting_summary_qwen(transcript: str):
#     """Generate meeting intelligence using Qwen3-27B Cloud API."""

#     return generate_meeting_summary(
#         transcript,
#         _llm_call=_call_qwen,
#         _llm_model=QWEN_MODEL,
#     )


# def generate_mindmap_qwen(transcript: str):
#     """Generate a mindmap using Qwen3-27B Cloud API."""

#     return generate_mindmap(
#         transcript,
#         _llm_call=_call_qwen,
#         _llm_model=QWEN_MODEL,
#     )

"""MeetMind - Meeting Intelligence

Mistral 128B API and Qwen3-27B API

Meeting summary, action items, timeline, and hierarchical mindmap.

"""

import json

import os

import re

from typing import Optional

import requests

from pydantic import BaseModel, Field

from mistral_client import call_mistral, MISTRAL_MODEL as DEFAULT_MISTRAL_MODEL

# ============================================================

# CONFIGURATION

# ============================================================

MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)

# Mistral long-context configuration used by mistral_client.py.

# This is the model/API context capacity we intend to support; the provider

# must also support 128K for this to work in practice.

MISTRAL_CONTEXT_WINDOW = int(os.getenv("MISTRAL_CONTEXT_WINDOW", "128000"))

MISTRAL_MAX_OUTPUT_TOKENS = int(os.getenv("MISTRAL_MAX_OUTPUT_TOKENS", "4096"))

QWEN_API_URL = os.getenv(

    "QWEN_API_URL",

    "http://115.112.206.245/api/chat/completions",

)

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

QWEN_MODEL = os.getenv("QWEN_MODEL", "ai-switch.qwen3-27b")

# Qwen3-27B long-context configuration.

# The configured Qwen API/model must support a 128K context window.

QWEN_CONTEXT_WINDOW = int(

    os.getenv("QWEN_CONTEXT_WINDOW", "128000")

)

QWEN_MAX_OUTPUT_TOKENS = int(

    os.getenv("QWEN_MAX_OUTPUT_TOKENS", "4096")

)

JSON_ONLY_INSTRUCTION = """

Return exactly one valid JSON object.

Do not include your thinking process, reasoning, introduction,

Markdown fences, or explanatory text before or after the JSON.

Use double quotes for JSON keys and strings.

Do not use trailing commas.

"""

# ============================================================

# PYDANTIC SCHEMAS

# ============================================================

class Task(BaseModel):

    task: str

    assignee: Optional[str] = None

    deadline: Optional[str] = None

class TimelineItem(BaseModel):

    action: str

    date: str

class MindMapNode(BaseModel):

    title: str

    children: list["MindMapNode"] = Field(default_factory=list)

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

# QWEN3-27B CLOUD API

# ============================================================

def _call_qwen(

    *,

    system_prompt: str,

    user_prompt: str,

    temperature: float = 0.0,

    max_tokens: int = QWEN_MAX_OUTPUT_TOKENS,

) -> str:

    """Call the configured Qwen3-27B API."""

    if not QWEN_API_URL:

        raise RuntimeError("QWEN_API_URL is not configured.")

    if not QWEN_API_KEY:

        raise RuntimeError("QWEN_API_KEY is not configured.")

    headers = {

        "Authorization": f"Bearer {QWEN_API_KEY}",

        "Content-Type": "application/json",

    }

    payload = {

        "model": QWEN_MODEL,

        "messages": [

            {

                "role": "system",

                "content": system_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,

            },

            {

                "role": "user",

                "content": user_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,

            },

        ],

        "temperature": temperature,

        "max_tokens": max_tokens,

        "context_window": QWEN_CONTEXT_WINDOW,

    }

    try:

        response = requests.post(

            QWEN_API_URL,

            headers=headers,

            json=payload,

            timeout=300,

        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as exc:

        raise RuntimeError(

            f"Qwen API request failed: {exc}"

        ) from exc

    except ValueError as exc:

        raise RuntimeError(

            "Qwen API returned an invalid HTTP JSON response."

        ) from exc

    try:

        content = data["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as exc:

        raise RuntimeError(

            f"Unexpected Qwen API response structure: {data}"

        ) from exc

    if not isinstance(content, str) or not content.strip():

        raise RuntimeError("Qwen API returned an empty response.")

    return content.strip()

# ============================================================

# ROBUST JSON EXTRACTION

# ============================================================

def _remove_thinking_content(text: str) -> str:

    """Remove common reasoning sections and surrounding Markdown."""

    text = re.sub(

        r"<think\b[^>]*>.*?</think\s*>",

        "",

        text,

        flags=re.IGNORECASE | re.DOTALL,

    )

    text = re.sub(

        r"<think\b[^>]*>.*$",

        "",

        text,

        flags=re.IGNORECASE | re.DOTALL,

    )

    text = re.sub(

        r"```(?:json|JSON)?[ \t]*",

        "",

        text,

    )

    text = text.replace("```", "")

    return text.strip()

def _extract_json_object(text: str, required_keys=None) -> str:

    """

    Extract one complete valid JSON object from an LLM response.

    The scanner respects quoted strings and escaped characters,

    so braces inside JSON strings do not break object detection.

    """

    if not isinstance(text, str) or not text.strip():

        raise ValueError("The model returned an empty response.")

    text = _remove_thinking_content(text)

    candidates = []

    length = len(text)

    for start, char in enumerate(text):

        if char != "{":

            continue

        depth = 0

        in_string = False

        escaped = False

        for end in range(start, length):

            current = text[end]

            if in_string:

                if escaped:

                    escaped = False

                elif current == "\\\\":

                    escaped = True

                elif current == '"':

                    in_string = False

                continue

            if current == '"':

                in_string = True

            elif current == "{":

                depth += 1

            elif current == "}":

                depth -= 1

                if depth == 0:

                    candidate = text[start:end + 1]

                    try:

                        parsed = json.loads(candidate)

                    except json.JSONDecodeError:

                        break

                    if isinstance(parsed, dict):

                        matching = (

                            required_keys is None

                            or required_keys.issubset(parsed.keys())

                        )

                        candidates.append(

                            (

                                matching,

                                len(candidate),

                                start,

                                candidate,

                            )

                        )

                    break

    if not candidates:

        raise ValueError(

            "No complete valid JSON object was found in the model response."

        )

    if required_keys:

        matching_candidates = [

            candidate

            for candidate in candidates

            if candidate[0]

        ]

        if matching_candidates:

            candidates = matching_candidates

    # Prefer the largest object matching the expected schema.

    # This helps avoid selecting a nested child object.

    selected = max(

        candidates,

        key=lambda candidate: (

            candidate[0],

            candidate[1],

            candidate[2],

        ),

    )

    return selected[3]

def _parse_mindmap_json(text: str) -> dict:

    """Parse and validate the root of a mindmap JSON object."""

    cleaned = _extract_json_object(

        text,

        required_keys={"title", "children"},

    )

    parsed = json.loads(cleaned)

    if not isinstance(parsed, dict):

        raise ValueError("Mindmap root must be a JSON object.")

    if not isinstance(parsed.get("title"), str):

        raise ValueError("Mindmap root must contain a title string.")

    if not parsed["title"].strip():

        raise ValueError("Mindmap root title cannot be empty.")

    if not isinstance(parsed.get("children"), list):

        raise ValueError("Mindmap children must be a list.")

    return parsed

# ============================================================

# MEETING INTELLIGENCE PROMPT

# ============================================================

SYSTEM_PROMPT = """

You are MeetMind, an AI meeting intelligence system.

Analyze the complete meeting transcript and return accurate,

professional meeting intelligence grounded in the transcript.

The transcript may contain English, Tamil, Tamil-English code-mixed

speech, Indian English, informal speech, and ASR errors.

Speaker diarization is disabled. Do not create speaker labels.

STRICT GROUNDING:

\\- Never invent names, tasks, assignees, deadlines, dates,

  decisions, objections, action items, or facts.

\\- Correct an ASR error only when the intended meaning is clear.

\\- Preserve important technical terminology.

TITLE:

Generate a short, meaningful title describing the actual meeting.

OBJECTIVE:

The objective is mandatory. Infer why the meeting was held from

the complete discussion. Never return an empty objective or a

generic refusal such as "Unknown" or "Not mentioned".

SUMMARY:

Write a professional executive-style summary, normally 3-6

sentences. Cover the main subject, important topics, current

status, problems, decisions, and next steps when present.

Do not merely copy the transcript.

TASKS:

Extract genuine work that needs to be completed.

Only assign a task to a named person explicitly identified

as responsible. Do not use pronouns such as "I" or "we"

as assignees. Use null if the responsible person's name

is not explicitly stated.

DEADLINES:

Only use explicitly stated deadlines or dates.

Never invent dates or infer a deadline from vague wording.

TIMELINE:

Include only actual actions with explicitly stated deadlines

or dates. Use an empty list if no such actions exist.

DECISIONS:

Include only decisions that were actually made.

OBJECTIONS:

Include genuine objections, disagreements, concerns, blockers,

or explicitly raised risks. Do not invent concerns.

ACTION ITEMS:

Include explicit follow-up actions. Do not invent actions.

Return exactly these fields:

title, objective, meeting_summary, tasks_assigned,

decision_points, objections, action_items, timeline.

The output must be a single valid JSON object.

"""

# ============================================================

# MEETING SUMMARY GENERATION

# ============================================================

def _normalize_meeting_result_data(data: dict) -> dict:
    """Normalize LLM meeting output to the MeetingResult schema."""
    if not isinstance(data, dict):
        raise ValueError("Meeting result must be a JSON object.")

    normalized = dict(data)

    action_items = normalized.get("action_items", [])
    if not isinstance(action_items, list):
        action_items = []
    normalized["action_items"] = []
    for item in action_items:
        if isinstance(item, str) and item.strip():
            normalized["action_items"].append(item.strip())
        elif isinstance(item, dict):
            text = item.get("action") or item.get("task") or item.get("description") or item.get("action_item")
            if isinstance(text, str) and text.strip():
                normalized["action_items"].append(text.strip())

    decision_points = normalized.get("decision_points", [])
    if not isinstance(decision_points, list):
        decision_points = []
    normalized["decision_points"] = []
    for item in decision_points:
        if isinstance(item, str) and item.strip():
            normalized["decision_points"].append(item.strip())
        elif isinstance(item, dict):
            text = item.get("decision") or item.get("description") or item.get("text")
            if isinstance(text, str) and text.strip():
                normalized["decision_points"].append(text.strip())

    objections = normalized.get("objections", [])
    if not isinstance(objections, list):
        objections = []
    normalized["objections"] = []
    for item in objections:
        if isinstance(item, str) and item.strip():
            normalized["objections"].append(item.strip())
        elif isinstance(item, dict):
            text = item.get("objection") or item.get("concern") or item.get("description") or item.get("text")
            if isinstance(text, str) and text.strip():
                normalized["objections"].append(text.strip())

    tasks = normalized.get("tasks_assigned", [])
    if not isinstance(tasks, list):
        tasks = []
    normalized_tasks = []
    for item in tasks:
        if isinstance(item, dict):
            task = item.get("task") or item.get("action") or item.get("description")
            if isinstance(task, str) and task.strip():
                normalized_tasks.append({
                    "task": task.strip(),
                    "assignee": item.get("assignee"),
                    "deadline": item.get("deadline"),
                })
        elif isinstance(item, str) and item.strip():
            normalized_tasks.append({"task": item.strip(), "assignee": None, "deadline": None})
    normalized["tasks_assigned"] = normalized_tasks

    timeline = normalized.get("timeline", [])
    if not isinstance(timeline, list):
        timeline = []
    normalized_timeline = []
    for item in timeline:
        if isinstance(item, dict):
            action = item.get("action") or item.get("task") or item.get("description")
            date = item.get("date")
            if isinstance(action, str) and action.strip():
                normalized_timeline.append({
                    "action": action.strip(),
                    "date": "" if date is None else str(date).strip(),
                })
    normalized["timeline"] = normalized_timeline
    return normalized

def generate_meeting_summary(

    transcript: str,

    _llm_call=call_mistral,

    _llm_model=MISTRAL_MODEL,

):

    """Generate meeting intelligence using the selected LLM."""

    transcript = (transcript or "").strip()

    if not transcript:

        raise ValueError("Cannot generate a summary from an empty transcript.")

    user_prompt = f"""

Analyze the COMPLETE meeting transcript.

Return a JSON object containing exactly these fields:

{{

  "title": "Meeting title",

  "objective": "Purpose of the meeting",

  "meeting_summary": "Professional meeting summary",

  "tasks_assigned": [

    {{

      "task": "Task description",

      "assignee": null,

      "deadline": null

    }}

  ],

  "decision_points": [],

  "objections": [],

  "action_items": [],

  "timeline": [

    {{

      "action": "Action with an explicit deadline",

      "date": "Explicit deadline or date"

    }}

  ]

}}

Use empty lists when no relevant items exist.

Use null for unknown task assignees and deadlines.

Do not invent information.

COMPLETE MEETING TRANSCRIPT:

\\============================

{transcript}

\\============================

Return only the JSON object.

"""

    try:

        content = _llm_call(

            system_prompt=SYSTEM_PROMPT,

            user_prompt=user_prompt,

            temperature=0.0,

            max_tokens=4096,

        )

    except Exception as exc:

        raise RuntimeError(

            f"Meeting summary generation failed for {_llm_model}: {exc}"

        ) from exc

    if not isinstance(content, str) or not content.strip():

        raise RuntimeError(

            f"{_llm_model} returned an empty meeting summary."

        )

    try:

        cleaned = _extract_json_object(

            content,

            required_keys={

                "title",

                "objective",

                "meeting_summary",

                "tasks_assigned",

                "decision_points",

                "objections",

                "action_items",

                "timeline",

            },

        )

        data = json.loads(cleaned)

        data = _normalize_meeting_result_data(data)

        result = MeetingResult.model_validate(data)

    except Exception as exc:

        raise RuntimeError(

            f"{_llm_model} returned invalid structured meeting output: {exc}"

        ) from exc

    if not result.objective.strip():

        raise RuntimeError(

            f"{_llm_model} returned an empty meeting objective."

        )

    return result.model_dump()

# ============================================================

# MINDMAP VALIDATION

# ============================================================

def _clean_mindmap_node(node: dict) -> dict:

    """Recursively validate and normalize mindmap nodes."""

    if not isinstance(node, dict):

        raise ValueError("Every mindmap node must be an object.")

    title = node.get("title")

    if not isinstance(title, str) or not title.strip():

        raise ValueError("Every mindmap node must have a non-empty title.")

    children = node.get("children", [])

    if not isinstance(children, list):

        raise ValueError(

            f"Children for node {title!r} must be a list."

        )

    cleaned = {

        "title": title.strip(),

        "children": [

            _clean_mindmap_node(child)

            for child in children

        ],

    }

    return cleaned

# ============================================================

# MINDMAP GENERATION

# ============================================================

MINDMAP_SYSTEM_PROMPT = """

You are MeetMind, a meeting mindmap generator.

Generate a hierarchical mindmap directly from the complete transcript.

Do not generate the mindmap from a summary.

Use only information supported by the transcript.

Do not invent names, decisions, tasks, deadlines, or facts.

Keep node titles concise and meaningful.

Every node must contain:

\\- title: a string

\\- children: an array of child nodes, which may be empty

Return exactly one JSON object with a root title and children.

Do not add any other fields.

Do not return reasoning, Markdown, introductions, or explanations.

"""

def generate_mindmap(

    transcript: str,

    _llm_call=call_mistral,

    _llm_model=MISTRAL_MODEL,

):

    """Generate a hierarchical mindmap directly from the transcript."""

    transcript = (transcript or "").strip()

    if not transcript:

        raise ValueError(

            "Cannot generate a mindmap because the transcript is empty."

        )

    user_prompt = f"""

Analyze the complete meeting transcript and create a hierarchical mindmap.

Capture relevant:

\\- Main topics

\\- Technical discussions

\\- Current status

\\- Problems or challenges

\\- Decisions

\\- Action items

\\- Tasks

\\- Explicit timelines

\\- Next steps

Only include categories supported by the transcript.

Return exactly this structure:

{{

  "title": "Main Meeting Topic",

  "children": [

    {{

      "title": "Major Topic",

      "children": [

        {{

          "title": "Important Detail",

          "children": []

        }}

      ]

    }}

  ]

}}

Every node must contain a title and a children array.

Do not include fields other than title and children.

COMPLETE MEETING TRANSCRIPT:

\\============================

{transcript}

\\============================

Return only one valid JSON object.

"""

    try:

        content = _llm_call(

            system_prompt=MINDMAP_SYSTEM_PROMPT,

            user_prompt=user_prompt,

            temperature=0.0,

            max_tokens=4096,

        )

    except Exception as exc:

        raise RuntimeError(

            f"Mindmap generation failed for {_llm_model}: {exc}"

        ) from exc

    if not isinstance(content, str) or not content.strip():

        raise RuntimeError(

            f"{_llm_model} returned an empty mindmap response."

        )

    try:

        mindmap_data = _parse_mindmap_json(content)

    except Exception as first_error:

        repair_prompt = f"""

Repair the following malformed mindmap response.

Requirements:

\\- Preserve the existing information.

\\- Do not invent new content.

\\- Return one valid JSON object.

\\- The root must contain title and children.

\\- Every node must contain title and children.

\\- Use only title and children fields.

\\- Do not include reasoning, Markdown, or explanations.

Malformed response:

{content}

Return only the repaired JSON object.

"""

        try:

            repaired_content = _llm_call(

                system_prompt=(

                    "You are a JSON repair engine. Return only one valid "

                    "mindmap JSON object. Do not explain anything."

                ),

                user_prompt=repair_prompt,

                temperature=0.0,

                max_tokens=4096,

            )

            mindmap_data = _parse_mindmap_json(repaired_content)

        except Exception as repair_error:

            raise RuntimeError(

                f"{_llm_model} returned invalid mindmap JSON, and "

                f"automatic repair failed. Original error: {first_error}. "

                f"Repair error: {repair_error}"

            ) from repair_error

    try:

        return _clean_mindmap_node(mindmap_data)

    except Exception as exc:

        raise RuntimeError(

            f"{_llm_model} returned an invalid mindmap structure: {exc}"

        ) from exc

# ============================================================

# QWEN3-27B WRAPPERS

# ============================================================

def generate_meeting_summary_qwen(transcript: str):

    """Generate meeting intelligence using Qwen3-27B Cloud API."""

    return generate_meeting_summary(

        transcript,

        _llm_call=_call_qwen,

        _llm_model=QWEN_MODEL,

    )

def generate_mindmap_qwen(transcript: str):

    """Generate a mindmap using Qwen3-27B Cloud API."""

    return generate_mindmap(

        transcript,

        _llm_call=_call_qwen,

        _llm_model=QWEN_MODEL,

    )
