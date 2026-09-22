"""
MeetMind - Meeting Intelligence

Flow:

    Complete transcript
        |
        +------------------------------+
        |                              |
        v                              v
    Mistral 128B API              Mistral 128B API
        |                              |
        v                              v
Meeting Intelligence              Mind Map
                                      |
                                      v
                             Hierarchical JSON

Speaker diarization: DISABLED
"""

import os
import re
import json
from typing import Optional

from mistral_client import call_mistral, MISTRAL_MODEL
from pydantic import BaseModel


# ============================================================
# CONFIGURATION
# ============================================================

MISTRAL_MODEL = os.getenv(
    "MISTRAL_MODEL",
    MISTRAL_MODEL,
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

    if len(value.split()) > 3:
        return False

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


# ============================================================
# MIND MAP SCHEMA
# ============================================================

class MindMapNode(BaseModel):
    title: str
    children: list["MindMapNode"] = []


# ============================================================
# MEETING INTELLIGENCE SCHEMA
# ============================================================

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
# MEETING INTELLIGENCE SYSTEM PROMPT
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

Rules:

1. Include ONLY actions with an explicitly mentioned deadline
   or date.

2. The action must correspond to an actual task/action discussed
   in the transcript.

3. Use the explicitly stated date/deadline.

4. Do NOT invent dates.

5. Do NOT infer dates.

6. Do NOT include tasks without a deadline.

7. Do NOT include general discussion points.

8. Do NOT include decisions unless they also represent an
   explicit action with a stated deadline.

If no action with a specific deadline/date is mentioned:

timeline = []


============================================================
8. DECISIONS
============================================================

Extract only decisions that were actually made.

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

Do not invent objections simply because a problem was discussed.

If no genuine objection or concern exists:

return []


============================================================
10. ACTION ITEMS
============================================================

Extract explicit follow-up actions resulting from the meeting.

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

    transcript = (transcript or "").strip()

    if not transcript:
        return {
            "title": "Untitled Meeting",
            "objective": (
                "No meeting objective can be generated "
                "because no transcript was provided."
            ),
            "meeting_summary": "No transcript was available.",
            "tasks_assigned": [],
            "decision_points": [],
            "objections": [],
            "action_items": [],
            "timeline": [],
        }

    print()
    print("=" * 70)
    print("MEETMIND - MISTRAL MEETING INTELLIGENCE")
    print("=" * 70)

    print("LLM Model:", MISTRAL_MODEL)
    print("Speaker diarization:", "DISABLED")
    print("Transcript length:", len(transcript), "characters")
    print("Analyzing COMPLETE transcript...")
    print("Generating meeting intelligence...")
    print("=" * 70)

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

    def _call_mistral(chat_messages):

        try:
            system_prompt = ""
            user_prompt = ""

            for message in chat_messages:

                role = message.get("role")
                content = message.get("content", "")

                if role == "system":
                    system_prompt = content

                elif role == "user":

                    if user_prompt:
                        user_prompt += "\n\n" + content
                    else:
                        user_prompt = content

                elif role == "assistant":

                    user_prompt += (
                        "\n\nPrevious assistant output:\n"
                        + content
                    )

            user_prompt += """

Return ONLY valid JSON matching this exact structure:

{
  "title": "string",
  "objective": "string",
  "meeting_summary": "string",
  "tasks_assigned": [
    {
      "task": "string",
      "assignee": "string or null",
      "deadline": "string or null"
    }
  ],
  "decision_points": ["string"],
  "objections": ["string"],
  "action_items": ["string"],
  "timeline": [
    {
      "action": "string",
      "date": "string"
    }
  ]
}

Do not add markdown.
Do not add explanations.
Do not add extra fields.
"""

            content = call_mistral(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=4096,
            )

        except Exception as exc:

            raise RuntimeError(
                "Could not connect to Mistral 128B. "
                f"Make sure the Mistral API is configured and "
                f"model '{MISTRAL_MODEL}' is available. "
                f"Original error: {exc}"
            ) from exc

        content = (content or "").strip()

        if not content:
            raise RuntimeError(
                "Mistral 128B returned an empty response."
            )

        if content.startswith("```"):

            content = re.sub(
                r"^```(?:json)?\s*",
                "",
                content,
                flags=re.IGNORECASE,
            )

            content = re.sub(
                r"\s*```$",
                "",
                content,
            ).strip()

        try:

            result = MeetingResult.model_validate_json(content)

            return result, content

        except Exception as exc:

            print()
            print("=" * 70)
            print("INVALID MISTRAL STRUCTURED OUTPUT")
            print("=" * 70)
            print(content)
            print("=" * 70)

            raise RuntimeError(
                "Mistral 128B returned invalid structured output: "
                f"{exc}"
            ) from exc

    meeting_result, raw_response = _call_mistral(messages)

    if _looks_like_refusal(meeting_result.objective):

        print()
        print("=" * 70)
        print("OBJECTIVE INVALID - RETRYING")
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

Return the complete JSON structure again, including:

title
objective
meeting_summary
tasks_assigned
decision_points
objections
action_items
timeline
""",
            },
        ]

        meeting_result, raw_response = _call_mistral(
            retry_messages
        )

    objective = (
        meeting_result.objective.strip()
        if meeting_result.objective
        else ""
    )

    if not objective or _looks_like_refusal(objective):

        raise RuntimeError(
            "Mistral 128B could not produce a valid meeting "
            "objective after retry."
        )

    title = (
        meeting_result.title.strip()
        if meeting_result.title
        else "Untitled Meeting"
    )

    meeting_summary = (
        meeting_result.meeting_summary.strip()
        if meeting_result.meeting_summary
        else "No summary available."
    )

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

        if task.assignee:

            assignee = task.assignee.strip()

            if _looks_like_real_name(assignee):
                item["assignee"] = assignee

        if task.deadline:

            deadline = task.deadline.strip()

            if (
                deadline
                and deadline.lower()
                not in _PLACEHOLDER_VALUES
            ):
                item["deadline"] = deadline

        result["tasks_assigned"].append(item)

    # ========================================================
    # DECISIONS
    # ========================================================

    for decision in meeting_result.decision_points:

        if not decision:
            continue

        decision = decision.strip()

        if decision:
            result["decision_points"].append(decision)

    # ========================================================
    # OBJECTIONS
    # ========================================================

    for objection in meeting_result.objections:

        if not objection:
            continue

        objection = objection.strip()

        if objection:
            result["objections"].append(objection)

    # ========================================================
    # ACTION ITEMS
    # ========================================================

    for action in meeting_result.action_items:

        if not action:
            continue

        action = action.strip()

        if action:
            result["action_items"].append(action)

    # ========================================================
    # TIMELINE
    # ========================================================

    for timeline_item in meeting_result.timeline:

        if not timeline_item:
            continue

        action = (timeline_item.action or "").strip()
        date = (timeline_item.date or "").strip()

        if not action:
            continue

        if not date:
            continue

        if date.lower() in _PLACEHOLDER_VALUES:
            continue

        result["timeline"].append(
            {
                "action": action,
                "date": date,
            }
        )

    # ========================================================
    # ADDITIONAL TIMELINE VALIDATION
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
                task_item.get("deadline") or ""
            ).strip().lower()

            if (
                timeline_action == task_text
                and task_deadline
                and task_deadline == timeline_date
            ):
                matched = True
                break

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

            print("-", task["task"])

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
        print("- No tasks identified.")

    print()
    print("DECISIONS:")

    if result["decision_points"]:

        for decision in result["decision_points"]:
            print("-", decision)

    else:
        print("- No decisions identified.")

    print()
    print("OBJECTIONS:")

    if result["objections"]:

        for objection in result["objections"]:
            print("-", objection)

    else:
        print("- None")

    print()
    print("ACTION ITEMS:")

    if result["action_items"]:

        for action in result["action_items"]:
            print("-", action)

    else:
        print("- No action items identified.")

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


# ============================================================
# MIND MAP SYSTEM PROMPT
# ============================================================

MINDMAP_SYSTEM_PROMPT = """
You are MeetMind, an AI meeting mind-map generator.

Your job is to analyze the COMPLETE meeting transcript and
generate a concise, accurate hierarchical mind map.

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

The transcript is the ONLY source of truth.

Use ONLY information supported by the transcript.

Never invent:

- people
- names
- tasks
- deadlines
- dates
- decisions
- technologies
- project details
- problems
- outcomes
- next steps

You may correct an obvious ASR error only when the intended
meaning is clear from the surrounding context.


============================================================
MIND MAP STRUCTURE
============================================================

The root node must represent the central topic of the meeting.

Create meaningful branches based ONLY on information actually
present in the transcript.

Possible branches include:

- Project Overview
- Key Discussions
- Technical Topics
- Current Status
- Problems / Challenges
- Decisions
- Action Items
- Tasks
- Timeline
- Next Steps

Do NOT force all categories into the mind map.

Only create branches that are supported by the transcript.


============================================================
NODE RULES
============================================================

1. Keep node titles concise.

2. Do not write paragraphs inside nodes.

3. Preserve important technical terminology.

4. Organize related information under the same branch.

5. Avoid unnecessary duplication.

6. Important action items may appear under "Action Items".

7. Explicit deadlines may appear under "Timeline".

8. Decisions may appear under "Decisions".

9. Problems or concerns may appear under
   "Problems / Challenges".

10. The mind map may contain multiple levels of children.

11. The mind map must represent the actual meeting content.

12. Do not infer information that is not supported by the
    transcript.


============================================================
IMPORTANT
============================================================

Generate the mind map DIRECTLY from the COMPLETE TRANSCRIPT.

DO NOT generate the mind map from a meeting summary.

DO NOT expect a summary to be provided.

The transcript itself is the source of truth.


============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

The structure must be:

{
  "title": "Main Meeting Topic",
  "children": [
    {
      "title": "Major Topic",
      "children": [
        {
          "title": "Important Detail"
        }
      ]
    }
  ]
}

Every node MUST contain:

"title"

A node MAY contain:

"children"

Do not add any other fields.

Do not add markdown.

Do not add explanations outside the JSON.

Do not copy the example information into the output unless
that information actually exists in the transcript.

JSON STRICTNESS RULES:

Return syntactically valid JSON.

Every opening { must have a matching }.
Every opening [ must have a matching ].

Every property must be separated by a comma.

All strings must use double quotes.

Never place an unescaped double quote inside a title.

Do not use trailing commas.

Do not output comments.

Do not output markdown fences.

Do not output any text before or after the JSON.

Keep node titles concise.

Maximum 6 top-level branches.
Maximum 5 children per branch.
Maximum 3 hierarchy levels below the root.
"""


# ============================================================
# MIND MAP VALIDATION
# ============================================================

def _clean_mindmap_node(node):

    if not isinstance(node, dict):

        raise ValueError(
            "Invalid mind-map node. "
            "Expected a JSON object."
        )

    title = node.get("title", "")

    if not isinstance(title, str):

        raise ValueError(
            "Invalid mind-map node title."
        )

    title = title.strip()

    if not title:

        raise ValueError(
            "Mind-map node title cannot be empty."
        )

    cleaned_node = {
        "title": title
    }

    children = node.get(
        "children",
        [],
    )

    if children is None:
        children = []

    if not isinstance(children, list):

        raise ValueError(
            "Mind-map children must be a list."
        )

    cleaned_children = []

    for child in children:

        cleaned_children.append(
            _clean_mindmap_node(child)
        )

    if cleaned_children:
        cleaned_node["children"] = cleaned_children

    return cleaned_node


# ============================================================
# GENERATE MIND MAP
# ============================================================

def generate_mindmap(transcript: str):
    """
    Generate a mind map directly from the complete transcript.

    This is completely independent from
    generate_meeting_summary().

    The meeting summary is NOT generated first.

    The transcript is sent directly to Mistral 128B.
    """

    transcript = (transcript or "").strip()

    if not transcript:

        raise ValueError(
            "Cannot generate mind map because transcript is empty."
        )

    print()
    print("=" * 70)
    print("MEETMIND - MISTRAL MIND MAP GENERATION")
    print("=" * 70)

    print("LLM Model:", MISTRAL_MODEL)
    print("Speaker diarization:", "DISABLED")
    print("Transcript length:", len(transcript), "characters")
    print(
        "Generating mind map directly from COMPLETE transcript..."
    )
    print("=" * 70)

    user_prompt = f"""
Analyze the COMPLETE meeting transcript below and generate
a hierarchical mind map.

IMPORTANT:

The transcript is the source of truth.

Generate the mind map DIRECTLY from the transcript.

Do NOT generate it from a meeting summary.

Do NOT invent information.

Capture the important:

- topics
- technical discussions
- current status
- problems or challenges
- decisions
- action items
- tasks
- explicit timelines
- next steps

Only include categories that are actually supported by
the transcript.

Keep node titles concise.

MEETING TRANSCRIPT

==================

{transcript}

==================

Return ONLY valid JSON in this exact structure:

{{
  "title": "Main Meeting Topic",
  "children": [
    {{
      "title": "Major Topic",
      "children": [
        {{
          "title": "Important Detail"
        }}
      ]
    }}
  ]
}}

Every node must contain a "title".

A node may contain "children".

Do not add any other fields.
Do not add markdown.
Do not add explanations.
"""

    try:

        content = call_mistral(
            system_prompt=MINDMAP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not connect to Mistral 128B while generating "
            f"the mind map. Make sure the Mistral API is configured "
            f"and model '{MISTRAL_MODEL}' is available. "
            f"Original error: {exc}"
        ) from exc

    content = (content or "").strip()

    if not content:

        raise RuntimeError(
            "Mistral 128B returned an empty mind-map response."
        )

    # --------------------------------------------------------
    # REMOVE MARKDOWN FENCES
    # --------------------------------------------------------

    if content.startswith("```"):

        content = re.sub(
            r"^```(?:json)?\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        content = re.sub(
            r"\s*```$",
            "",
            content,
        ).strip()

    # ========================================================
    # ROBUST MIND-MAP JSON PARSING
    # ========================================================

    def _extract_json_object(text):
        """
        Extract the outermost JSON object from the Mistral response.

        Handles accidental surrounding text and markdown fences.
        """

        text = (text or "").strip()

        if not text:
            return ""

        # Remove markdown fences.
        text = re.sub(
            r"^```(?:json)?\\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\\s*```$",
            "",
            text,
        ).strip()

        # Already a JSON object.
        if text.startswith("{") and text.endswith("}"):
            return text

        # Extract the outer JSON object if Mistral added text
        # before or after the JSON.
        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if (
            first_brace >= 0
            and last_brace > first_brace
        ):
            return text[
                first_brace:last_brace + 1
            ].strip()

        return text

    def _parse_mindmap_json(text):
        """
        Parse the Mistral response as JSON.
        """

        cleaned = _extract_json_object(text)

        if not cleaned:
            raise json.JSONDecodeError(
                "Empty mind-map response",
                "",
                0,
            )

        return json.loads(cleaned)

    # --------------------------------------------------------
    # FIRST JSON PARSE
    # --------------------------------------------------------

    try:

        mindmap_data = _parse_mindmap_json(
            content
        )

    except json.JSONDecodeError as first_error:

        # ----------------------------------------------------
        # AUTOMATIC JSON REPAIR
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("MIND MAP JSON INVALID")
        print("REQUESTING JSON REPAIR FROM MISTRAL")
        print("=" * 70)

        repair_prompt = f"""
The following response was intended to be a JSON mind map,
but it contains a JSON syntax error.

Repair ONLY the JSON syntax.

IMPORTANT RULES:

1. Preserve all existing information.
2. Do NOT invent information.
3. Do NOT remove valid information.
4. Do NOT summarize the content.
5. Do NOT change node titles unless required for valid JSON.
6. Do NOT add markdown.
7. Do NOT add explanations.
8. Return ONLY valid JSON.
9. Every node must contain "title".
10. A node may contain "children".
11. Do not add fields other than "title" and "children".
12. Use double quotes for all JSON strings.
13. Do not use trailing commas.
14. Properly close every object and array.

Required structure:

{{
  "title": "Main Meeting Topic",
  "children": [
    {{
      "title": "Major Topic",
      "children": [
        {{
          "title": "Important Detail"
        }}
      ]
    }}
  ]
}}

INVALID RESPONSE:

{content}

Return ONLY the corrected JSON.
"""

        try:

            repaired_content = call_mistral(
                system_prompt="""
You are a strict JSON repair engine for MeetMind.

Your only task is to repair malformed JSON.

Preserve the information exactly.
Do not add information.
Do not remove information.
Do not explain anything.

Return ONLY syntactically valid JSON.
""",
                user_prompt=repair_prompt,
                temperature=0.0,
                max_tokens=4096,
            )

        except Exception as repair_exc:

            raise RuntimeError(
                "Mistral 128B mind-map JSON was invalid "
                "and the automatic JSON repair request failed: "
                f"{repair_exc}"
            ) from repair_exc

        repaired_content = (
            repaired_content or ""
        ).strip()

        if not repaired_content:

            raise RuntimeError(
                "Mistral 128B returned an empty response "
                "during mind-map JSON repair."
            )

        try:

            mindmap_data = _parse_mindmap_json(
                repaired_content
            )

            print()
            print("=" * 70)
            print("MIND MAP JSON REPAIRED SUCCESSFULLY")
            print("=" * 70)

        except json.JSONDecodeError as repair_error:

            print()
            print("=" * 70)
            print("MIND MAP JSON REPAIR FAILED")
            print("=" * 70)
            print(
                "Original JSON error:",
                first_error,
            )
            print(
                "Repair JSON error:",
                repair_error,
            )
            print()
            print("Original response:")
            print(content)
            print()
            print("Repair response:")
            print(repaired_content)
            print("=" * 70)

            raise RuntimeError(
                "Mistral 128B returned invalid mind-map JSON "
                "and automatic JSON repair also failed: "
                f"{repair_error}"
            ) from repair_error

    # --------------------------------------------------------
    # VALIDATE ROOT
    # --------------------------------------------------------

    if not isinstance(
        mindmap_data,
        dict,
    ):

        raise RuntimeError(
            "Mistral 128B mind-map response must be a JSON object."
        )

    # --------------------------------------------------------
    # CLEAN / VALIDATE TREE
    # --------------------------------------------------------

    try:

        mindmap = _clean_mindmap_node(
            mindmap_data
        )

    except Exception as exc:

        raise RuntimeError(
            "Mistral 128B returned an invalid mind-map structure: "
            f"{exc}"
        ) from exc

    # --------------------------------------------------------
    # LOG RESULT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("MIND MAP GENERATED SUCCESSFULLY")
    print("=" * 70)

    print()
    print("ROOT:")
    print(mindmap["title"])

    print()
    print(
        "TOP-LEVEL BRANCHES:",
        len(
            mindmap.get(
                "children",
                [],
            )
        ),
    )

    print()
    print("=" * 70)

    return mindmap