# # """MeetMind - Meeting Intelligence
# # Mistral 128B API and Qwen3-27B API
# # Meeting summary, action items, timeline, and hierarchical mindmap.
# # """
# # import json
# # import os
# # import re
# # from typing import Optional
# # import requests
# # from pydantic import BaseModel, Field
# # from mistral_client import call_mistral, MISTRAL_MODEL as DEFAULT_MISTRAL_MODEL
# # # ============================================================
# # # CONFIGURATION
# # # ============================================================
# # MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)
# # # Mistral long-context configuration used by mistral_client.py.
# # # This is the model/API context capacity we intend to support; the provider
# # # must also support 128K for this to work in practice.
# # MISTRAL_CONTEXT_WINDOW = int(os.getenv("MISTRAL_CONTEXT_WINDOW", "128000"))
# # MISTRAL_MAX_OUTPUT_TOKENS = int(os.getenv("MISTRAL_MAX_OUTPUT_TOKENS", "4096"))
# # QWEN_API_URL = os.getenv(
# #     "QWEN_API_URL",
# #     "http://115.112.206.245/api/chat/completions",
# # )
# # QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
# # QWEN_MODEL = os.getenv("QWEN_MODEL", "ai-switch.qwen3-27b")
# # # Qwen3-27B long-context configuration.
# # # The configured Qwen API/model must support a 128K context window.
# # QWEN_CONTEXT_WINDOW = int(
# #     os.getenv("QWEN_CONTEXT_WINDOW", "128000")
# # )
# # QWEN_MAX_OUTPUT_TOKENS = int(
# #     os.getenv("QWEN_MAX_OUTPUT_TOKENS", "4096")
# # )
# # JSON_ONLY_INSTRUCTION = """
# # Return exactly one valid JSON object.
# # Do not include your thinking process, reasoning, introduction,
# # Markdown fences, or explanatory text before or after the JSON.
# # Use double quotes for JSON keys and strings.
# # Do not use trailing commas.
# # """
# # # ============================================================
# # # PYDANTIC SCHEMAS
# # # ============================================================
# # class Task(BaseModel):
# #     task: str
# #     assignee: Optional[str] = None
# #     deadline: Optional[str] = None
# # class TimelineItem(BaseModel):
# #     action: str
# #     date: str
# # class MindMapNode(BaseModel):
# #     title: str
# #     children: list["MindMapNode"] = Field(default_factory=list)
# # class MeetingResult(BaseModel):
# #     title: str
# #     objective: str
# #     meeting_summary: str
# #     tasks_assigned: list[Task]
# #     decision_points: list[str]
# #     objections: list[str]
# #     action_items: list[str]
# #     timeline: list[TimelineItem]
# # # ============================================================
# # # QWEN3-27B CLOUD API
# # # ============================================================
# # def _call_qwen(
# #     *,
# #     system_prompt: str,
# #     user_prompt: str,
# #     temperature: float = 0.0,
# #     max_tokens: int = QWEN_MAX_OUTPUT_TOKENS,
# # ) -> str:
# #     """Call the configured Qwen3-27B API."""
# #     if not QWEN_API_URL:
# #         raise RuntimeError("QWEN_API_URL is not configured.")
# #     if not QWEN_API_KEY:
# #         raise RuntimeError("QWEN_API_KEY is not configured.")
# #     headers = {
# #         "Authorization": f"Bearer {QWEN_API_KEY}",
# #         "Content-Type": "application/json",
# #     }
# #     payload = {
# #         "model": QWEN_MODEL,
# #         "messages": [
# #             {
# #                 "role": "system",
# #                 "content": system_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
# #             },
# #             {
# #                 "role": "user",
# #                 "content": user_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
# #             },
# #         ],
# #         "temperature": temperature,
# #         "max_tokens": max_tokens,
# #         "context_window": QWEN_CONTEXT_WINDOW,
# #     }
# #     try:
# #         response = requests.post(
# #             QWEN_API_URL,
# #             headers=headers,
# #             json=payload,
# #             timeout=300,
# #         )
# #         response.raise_for_status()
# #         data = response.json()
# #     except requests.RequestException as exc:
# #         raise RuntimeError(
# #             f"Qwen API request failed: {exc}"
# #         ) from exc
# #     except ValueError as exc:
# #         raise RuntimeError(
# #             "Qwen API returned an invalid HTTP JSON response."
# #         ) from exc
# #     try:
# #         content = data["choices"][0]["message"]["content"]
# #     except (KeyError, IndexError, TypeError) as exc:
# #         raise RuntimeError(
# #             f"Unexpected Qwen API response structure: {data}"
# #         ) from exc
# #     if not isinstance(content, str) or not content.strip():
# #         raise RuntimeError("Qwen API returned an empty response.")
# #     return content.strip()
# # # ============================================================
# # # ROBUST JSON EXTRACTION
# # # ============================================================
# # def _remove_thinking_content(text: str) -> str:
# #     """Remove common reasoning sections and surrounding Markdown."""
# #     text = re.sub(
# #         r"<think\b[^>]*>.*?</think\s*>",
# #         "",
# #         text,
# #         flags=re.IGNORECASE | re.DOTALL,
# #     )
# #     text = re.sub(
# #         r"<think\b[^>]*>.*$",
# #         "",
# #         text,
# #         flags=re.IGNORECASE | re.DOTALL,
# #     )
# #     text = re.sub(
# #         r"```(?:json|JSON)?[ \t]*",
# #         "",
# #         text,
# #     )
# #     text = text.replace("```", "")
# #     return text.strip()
# # def _extract_json_object(text: str, required_keys=None) -> str:
# #     """
# #     Extract one complete valid JSON object from an LLM response.
# #     The scanner respects quoted strings and escaped characters,
# #     so braces inside JSON strings do not break object detection.
# #     """
# #     if not isinstance(text, str) or not text.strip():
# #         raise ValueError("The model returned an empty response.")
# #     text = _remove_thinking_content(text)
# #     candidates = []
# #     length = len(text)
# #     for start, char in enumerate(text):
# #         if char != "{":
# #             continue
# #         depth = 0
# #         in_string = False
# #         escaped = False
# #         for end in range(start, length):
# #             current = text[end]
# #             if in_string:
# #                 if escaped:
# #                     escaped = False
# #                 elif current == "\\\\":
# #                     escaped = True
# #                 elif current == '"':
# #                     in_string = False
# #                 continue
# #             if current == '"':
# #                 in_string = True
# #             elif current == "{":
# #                 depth += 1
# #             elif current == "}":
# #                 depth -= 1
# #                 if depth == 0:
# #                     candidate = text[start:end + 1]
# #                     try:
# #                         parsed = json.loads(candidate)
# #                     except json.JSONDecodeError:
# #                         break
# #                     if isinstance(parsed, dict):
# #                         matching = (
# #                             required_keys is None
# #                             or required_keys.issubset(parsed.keys())
# #                         )
# #                         candidates.append(
# #                             (
# #                                 matching,
# #                                 len(candidate),
# #                                 start,
# #                                 candidate,
# #                             )
# #                         )
# #                     break
# #     if not candidates:
# #         raise ValueError(
# #             "No complete valid JSON object was found in the model response."
# #         )
# #     if required_keys:
# #         matching_candidates = [
# #             candidate
# #             for candidate in candidates
# #             if candidate[0]
# #         ]
# #         if matching_candidates:
# #             candidates = matching_candidates
# #     # Prefer the largest object matching the expected schema.
# #     # This helps avoid selecting a nested child object.
# #     selected = max(
# #         candidates,
# #         key=lambda candidate: (
# #             candidate[0],
# #             candidate[1],
# #             candidate[2],
# #         ),
# #     )
# #     return selected[3]
# # def _parse_mindmap_json(text: str) -> dict:
# #     """Parse and validate the root of a mindmap JSON object."""
# #     cleaned = _extract_json_object(
# #         text,
# #         required_keys={"title", "children"},
# #     )
# #     parsed = json.loads(cleaned)
# #     if not isinstance(parsed, dict):
# #         raise ValueError("Mindmap root must be a JSON object.")
# #     if not isinstance(parsed.get("title"), str):
# #         raise ValueError("Mindmap root must contain a title string.")
# #     if not parsed["title"].strip():
# #         raise ValueError("Mindmap root title cannot be empty.")
# #     if not isinstance(parsed.get("children"), list):
# #         raise ValueError("Mindmap children must be a list.")
# #     return parsed
# # # ============================================================
# # # MEETING INTELLIGENCE PROMPT
# # # ============================================================
# # SYSTEM_PROMPT = """
# # You are MeetMind, an AI meeting intelligence system.
# # Analyze the complete meeting transcript and return accurate,
# # professional meeting intelligence grounded in the transcript.
# # The transcript may contain English, Tamil, Tamil-English code-mixed
# # speech, Indian English, informal speech, and ASR errors.
# # Speaker diarization is disabled. Do not create speaker labels.
# # STRICT GROUNDING:
# # \\- Never invent names, tasks, assignees, deadlines, dates,
# #   decisions, objections, action items, or facts.
# # \\- Correct an ASR error only when the intended meaning is clear.
# # \\- Preserve important technical terminology.
# # TITLE:
# # Generate a short, meaningful title describing the actual meeting.
# # OBJECTIVE:
# # The objective is mandatory. Infer why the meeting was held from
# # the complete discussion. Never return an empty objective or a
# # generic refusal such as "Unknown" or "Not mentioned".
# # SUMMARY:
# # Write a professional executive-style summary, normally 3-6
# # sentences. Cover the main subject, important topics, current
# # status, problems, decisions, and next steps when present.
# # Do not merely copy the transcript.
# # TASKS:
# # Extract genuine work that needs to be completed.
# # Only assign a task to a named person explicitly identified
# # as responsible. Do not use pronouns such as "I" or "we"
# # as assignees. Use null if the responsible person's name
# # is not explicitly stated.
# # DEADLINES:
# # Only use explicitly stated deadlines or dates.
# # Never invent dates or infer a deadline from vague wording.
# # TIMELINE:
# # Include only actual actions with explicitly stated deadlines
# # or dates. Use an empty list if no such actions exist.
# # DECISIONS:
# # Include only decisions that were actually made.
# # OBJECTIONS:
# # Include genuine objections, disagreements, concerns, blockers,
# # or explicitly raised risks. Do not invent concerns.
# # ACTION ITEMS:
# # Include explicit follow-up actions. Do not invent actions.
# # Return exactly these fields:
# # title, objective, meeting_summary, tasks_assigned,
# # decision_points, objections, action_items, timeline.
# # The output must be a single valid JSON object.
# # """
# # # ============================================================
# # # MEETING SUMMARY GENERATION
# # # ============================================================
# # def _normalize_meeting_result_data(data: dict) -> dict:
# #     """Normalize LLM meeting output to the MeetingResult schema."""
# #     if not isinstance(data, dict):
# #         raise ValueError("Meeting result must be a JSON object.")
# #     normalized = dict(data)
# #     action_items = normalized.get("action_items", [])
# #     if not isinstance(action_items, list):
# #         action_items = []
# #     normalized["action_items"] = []
# #     for item in action_items:
# #         if isinstance(item, str) and item.strip():
# #             normalized["action_items"].append(item.strip())
# #         elif isinstance(item, dict):
# #             text = item.get("action") or item.get("task") or item.get("description") or item.get("action_item")
# #             if isinstance(text, str) and text.strip():
# #                 normalized["action_items"].append(text.strip())
# #     decision_points = normalized.get("decision_points", [])
# #     if not isinstance(decision_points, list):
# #         decision_points = []
# #     normalized["decision_points"] = []
# #     for item in decision_points:
# #         if isinstance(item, str) and item.strip():
# #             normalized["decision_points"].append(item.strip())
# #         elif isinstance(item, dict):
# #             text = item.get("decision") or item.get("description") or item.get("text")
# #             if isinstance(text, str) and text.strip():
# #                 normalized["decision_points"].append(text.strip())
# #     objections = normalized.get("objections", [])
# #     if not isinstance(objections, list):
# #         objections = []
# #     normalized["objections"] = []
# #     for item in objections:
# #         if isinstance(item, str) and item.strip():
# #             normalized["objections"].append(item.strip())
# #         elif isinstance(item, dict):
# #             text = item.get("objection") or item.get("concern") or item.get("description") or item.get("text")
# #             if isinstance(text, str) and text.strip():
# #                 normalized["objections"].append(text.strip())
# #     tasks = normalized.get("tasks_assigned", [])
# #     if not isinstance(tasks, list):
# #         tasks = []
# #     normalized_tasks = []
# #     for item in tasks:
# #         if isinstance(item, dict):
# #             task = item.get("task") or item.get("action") or item.get("description")
# #             if isinstance(task, str) and task.strip():
# #                 normalized_tasks.append({
# #                     "task": task.strip(),
# #                     "assignee": item.get("assignee"),
# #                     "deadline": item.get("deadline"),
# #                 })
# #         elif isinstance(item, str) and item.strip():
# #             normalized_tasks.append({"task": item.strip(), "assignee": None, "deadline": None})
# #     normalized["tasks_assigned"] = normalized_tasks
# #     timeline = normalized.get("timeline", [])
# #     if not isinstance(timeline, list):
# #         timeline = []
# #     normalized_timeline = []
# #     for item in timeline:
# #         if isinstance(item, dict):
# #             action = item.get("action") or item.get("task") or item.get("description")
# #             date = item.get("date")
# #             if isinstance(action, str) and action.strip():
# #                 normalized_timeline.append({
# #                     "action": action.strip(),
# #                     "date": "" if date is None else str(date).strip(),
# #                 })
# #     normalized["timeline"] = normalized_timeline
# #     return normalized
# # def generate_meeting_summary(
# #     transcript: str,
# #     _llm_call=call_mistral,
# #     _llm_model=MISTRAL_MODEL,
# # ):
# #     """Generate meeting intelligence using the selected LLM."""
# #     transcript = (transcript or "").strip()
# #     if not transcript:
# #         raise ValueError("Cannot generate a summary from an empty transcript.")
# #     user_prompt = f"""
# # Analyze the COMPLETE meeting transcript.
# # Return a JSON object containing exactly these fields:
# # {{
# #   "title": "Meeting title",
# #   "objective": "Purpose of the meeting",
# #   "meeting_summary": "Professional meeting summary",
# #   "tasks_assigned": [
# #     {{
# #       "task": "Task description",
# #       "assignee": null,
# #       "deadline": null
# #     }}
# #   ],
# #   "decision_points": [],
# #   "objections": [],
# #   "action_items": [],
# #   "timeline": [
# #     {{
# #       "action": "Action with an explicit deadline",
# #       "date": "Explicit deadline or date"
# #     }}
# #   ]
# # }}
# # Use empty lists when no relevant items exist.
# # Use null for unknown task assignees and deadlines.
# # Do not invent information.
# # COMPLETE MEETING TRANSCRIPT:
# # \\============================
# # {transcript}
# # \\============================
# # Return only the JSON object.
# # """
# #     try:
# #         content = _llm_call(
# #             system_prompt=SYSTEM_PROMPT,
# #             user_prompt=user_prompt,
# #             temperature=0.0,
# #             max_tokens=4096,
# #         )
# #     except Exception as exc:
# #         raise RuntimeError(
# #             f"Meeting summary generation failed for {_llm_model}: {exc}"
# #         ) from exc
# #     if not isinstance(content, str) or not content.strip():
# #         raise RuntimeError(
# #             f"{_llm_model} returned an empty meeting summary."
# #         )
# #     try:
# #         cleaned = _extract_json_object(
# #             content,
# #             required_keys={
# #                 "title",
# #                 "objective",
# #                 "meeting_summary",
# #                 "tasks_assigned",
# #                 "decision_points",
# #                 "objections",
# #                 "action_items",
# #                 "timeline",
# #             },
# #         )
# #         data = json.loads(cleaned)
# #         data = _normalize_meeting_result_data(data)
# #         result = MeetingResult.model_validate(data)
# #     except Exception as exc:
# #         raise RuntimeError(
# #             f"{_llm_model} returned invalid structured meeting output: {exc}"
# #         ) from exc
# #     if not result.objective.strip():
# #         raise RuntimeError(
# #             f"{_llm_model} returned an empty meeting objective."
# #         )
# #     return result.model_dump()
# # # ============================================================
# # # MINDMAP VALIDATION
# # # ============================================================
# # def _clean_mindmap_node(node: dict) -> dict:
# #     """Recursively validate and normalize mindmap nodes."""
# #     if not isinstance(node, dict):
# #         raise ValueError("Every mindmap node must be an object.")
# #     title = node.get("title")
# #     if not isinstance(title, str) or not title.strip():
# #         raise ValueError("Every mindmap node must have a non-empty title.")
# #     children = node.get("children", [])
# #     if not isinstance(children, list):
# #         raise ValueError(
# #             f"Children for node {title!r} must be a list."
# #         )
# #     cleaned = {
# #         "title": title.strip(),
# #         "children": [
# #             _clean_mindmap_node(child)
# #             for child in children
# #         ],
# #     }
# #     return cleaned
# # # ============================================================
# # # MINDMAP GENERATION
# # # ============================================================
# # MINDMAP_SYSTEM_PROMPT = """
# # You are MeetMind, a meeting mindmap generator.
# # Generate a hierarchical mindmap directly from the complete transcript.
# # Do not generate the mindmap from a summary.
# # Use only information supported by the transcript.
# # Do not invent names, decisions, tasks, deadlines, or facts.
# # Keep node titles concise and meaningful.
# # Every node must contain:
# # \\- title: a string
# # \\- children: an array of child nodes, which may be empty
# # Return exactly one JSON object with a root title and children.
# # Do not add any other fields.
# # Do not return reasoning, Markdown, introductions, or explanations.
# # """
# # def generate_mindmap(
# #     transcript: str,
# #     _llm_call=call_mistral,
# #     _llm_model=MISTRAL_MODEL,
# # ):
# #     """Generate a hierarchical mindmap directly from the transcript."""
# #     transcript = (transcript or "").strip()
# #     if not transcript:
# #         raise ValueError(
# #             "Cannot generate a mindmap because the transcript is empty."
# #         )
# #     user_prompt = f"""
# # Analyze the complete meeting transcript and create a hierarchical mindmap.
# # Capture relevant:
# # \\- Main topics
# # \\- Technical discussions
# # \\- Current status
# # \\- Problems or challenges
# # \\- Decisions
# # \\- Action items
# # \\- Tasks
# # \\- Explicit timelines
# # \\- Next steps
# # Only include categories supported by the transcript.
# # Return exactly this structure:
# # {{
# #   "title": "Main Meeting Topic",
# #   "children": [
# #     {{
# #       "title": "Major Topic",
# #       "children": [
# #         {{
# #           "title": "Important Detail",
# #           "children": []
# #         }}
# #       ]
# #     }}
# #   ]
# # }}
# # Every node must contain a title and a children array.
# # Do not include fields other than title and children.
# # COMPLETE MEETING TRANSCRIPT:
# # \\============================
# # {transcript}
# # \\============================
# # Return only one valid JSON object.
# # """
# #     try:
# #         content = _llm_call(
# #             system_prompt=MINDMAP_SYSTEM_PROMPT,
# #             user_prompt=user_prompt,
# #             temperature=0.0,
# #             max_tokens=4096,
# #         )
# #     except Exception as exc:
# #         raise RuntimeError(
# #             f"Mindmap generation failed for {_llm_model}: {exc}"
# #         ) from exc
# #     if not isinstance(content, str) or not content.strip():
# #         raise RuntimeError(
# #             f"{_llm_model} returned an empty mindmap response."
# #         )
# #     try:
# #         mindmap_data = _parse_mindmap_json(content)
# #     except Exception as first_error:
# #         repair_prompt = f"""
# # Repair the following malformed mindmap response.
# # Requirements:
# # \\- Preserve the existing information.
# # \\- Do not invent new content.
# # \\- Return one valid JSON object.
# # \\- The root must contain title and children.
# # \\- Every node must contain title and children.
# # \\- Use only title and children fields.
# # \\- Do not include reasoning, Markdown, or explanations.
# # Malformed response:
# # {content}
# # Return only the repaired JSON object.
# # """
# #         try:
# #             repaired_content = _llm_call(
# #                 system_prompt=(
# #                     "You are a JSON repair engine. Return only one valid "
# #                     "mindmap JSON object. Do not explain anything."
# #                 ),
# #                 user_prompt=repair_prompt,
# #                 temperature=0.0,
# #                 max_tokens=4096,
# #             )
# #             mindmap_data = _parse_mindmap_json(repaired_content)
# #         except Exception as repair_error:
# #             raise RuntimeError(
# #                 f"{_llm_model} returned invalid mindmap JSON, and "
# #                 f"automatic repair failed. Original error: {first_error}. "
# #                 f"Repair error: {repair_error}"
# #             ) from repair_error
# #     try:
# #         return _clean_mindmap_node(mindmap_data)
# #     except Exception as exc:
# #         raise RuntimeError(
# #             f"{_llm_model} returned an invalid mindmap structure: {exc}"
# #         ) from exc
# # # ============================================================
# # # QWEN3-27B WRAPPERS
# # # ============================================================
# # def generate_meeting_summary_qwen(transcript: str):
# #     """Generate meeting intelligence using Qwen3-27B Cloud API."""
# #     return generate_meeting_summary(
# #         transcript,
# #         _llm_call=_call_qwen,
# #         _llm_model=QWEN_MODEL,
# #     )
# # def generate_mindmap_qwen(transcript: str):
# #     """Generate a mindmap using Qwen3-27B Cloud API."""
# #     return generate_mindmap(
# #         transcript,
# #         _llm_call=_call_qwen,
# #         _llm_model=QWEN_MODEL,
# #     )

# """MeetMind - Meeting Intelligence
# Mistral 128B API and Qwen3-27B API
# Meeting summary, tasks, decisions, action items, and hierarchical mindmap.
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
# # Mistral long-context configuration used by mistral_client.py.
# # This is the model/API context capacity we intend to support; the provider
# # must also support 128K for this to work in practice.
# MISTRAL_CONTEXT_WINDOW = int(os.getenv("MISTRAL_CONTEXT_WINDOW", "128000"))
# MISTRAL_MAX_OUTPUT_TOKENS = int(os.getenv("MISTRAL_MAX_OUTPUT_TOKENS", "4096"))
# QWEN_API_URL = os.getenv(
#        "QWEN_API_URL",
#        "http://115.112.206.245/api/chat/completions",
# )
# QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
# QWEN_MODEL = os.getenv("QWEN_MODEL", "ai-switch.qwen3-27b")
# # Qwen3-27B long-context configuration.
# # The configured Qwen API/model must support a 128K context window.
# QWEN_CONTEXT_WINDOW = int(
#        os.getenv("QWEN_CONTEXT_WINDOW", "128000")
# )
# QWEN_MAX_OUTPUT_TOKENS = int(
#        os.getenv("QWEN_MAX_OUTPUT_TOKENS", "4096")
# )
# JSON_ONLY_INSTRUCTION = """
# Return exactly one valid JSON object.
# Do not include your thinking process, reasoning, introduction,
# Markdown fences, or explanatory text before or after the JSON.
# Use double quotes for JSON keys and strings.
# Do not use trailing commas.
# """

# # ============================================================
# # DATE NORMALIZATION
# # ============================================================

# _MONTHS = (
#     "January February March April May June July August September "
#     "October November December"
# ).split()

# _MONTH_PATTERN = "|".join(_MONTHS)


# def format_deadline(value):
#     """
#     Normalize a date/deadline for display without a year.

#     Examples:
#       2023-10-17 -> October 17
#       October 17th, 2023 -> October 17
#       17 October 2023 -> October 17
#       October 17 -> October 17

#     Does not invent or infer a date. If a value cannot safely be recognized
#     as a date, it is returned unchanged except for surrounding whitespace.
#     """
#     if value is None:
#         return None
#     if not isinstance(value, str):
#         value = str(value)
#     text = value.strip()
#     if not text:
#         return None

#     # ISO date or ISO datetime. Keep the actual month/day; drop the year.
#     match = re.fullmatch(
#         r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[Tt ].*)?", text
#     )
#     if match:
#         month, day = int(match.group(2)), int(match.group(3))
#         if 1 <= month <= 12 and 1 <= day <= 31:
#             return f"{_MONTHS[month - 1]} {day}"

#     # Month DD[st/nd/rd/th][, YYYY] or Month DD, YYYY
#     match = re.fullmatch(
#         rf"({_MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
#         rf"(?:,?\s+\d{{4}})?",
#         text,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         month_name = next(m for m in _MONTHS if m.lower() == match.group(1).lower())
#         day = int(match.group(2))
#         if 1 <= day <= 31:
#             return f"{month_name} {day}"

#     # DD Month [YYYY]
#     match = re.fullmatch(
#         rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})(?:,?\s+\d{{4}})?",
#         text,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         day = int(match.group(1))
#         month_name = next(m for m in _MONTHS if m.lower() == match.group(2).lower())
#         if 1 <= day <= 31:
#             return f"{month_name} {day}"

#     return text


# def _normalize_dates_in_text(value):
#     """Remove years from recognizable dates embedded in report text."""
#     if not isinstance(value, str) or not value:
#         return value

#     # Convert ISO dates/datetimes anywhere in a string.
#     value = re.sub(
#         r"\b\d{4}-\d{1,2}-\d{1,2}(?:[Tt ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b",
#         lambda m: format_deadline(m.group(0)),
#         value,
#     )

#     # Convert month-first dates with ordinal suffix and optional year.
#     value = re.sub(
#         rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}})(st|nd|rd|th)?"
#         rf"(,?\s+\d{{4}})?\b",
#         lambda m: format_deadline(m.group(1) + " " + m.group(2)),
#         value,
#         flags=re.IGNORECASE,
#     )

#     # Convert day-first dates with optional year.
#     value = re.sub(
#         rf"\b(\d{{1,2}})(st|nd|rd|th)?\s+({_MONTH_PATTERN})(,?\s+\d{{4}})?\b",
#         lambda m: format_deadline(m.group(1) + " " + m.group(3)),
#         value,
#         flags=re.IGNORECASE,
#     )
#     return value


# def _normalize_dates_recursively(value):
#     """Normalize date strings throughout summary data and mindmap nodes."""
#     if isinstance(value, str):
#         return _normalize_dates_in_text(value)
#     if isinstance(value, list):
#         return [_normalize_dates_recursively(item) for item in value]
#     if isinstance(value, dict):
#         return {key: _normalize_dates_recursively(item) for key, item in value.items()}
#     return value


# # ============================================================
# # PYDANTIC SCHEMAS
# # ============================================================
# class Task(BaseModel):
#        task: str
#        assignee: Optional[str] = None
#        deadline: Optional[str] = None
# class MindMapNode(BaseModel):
#        title: str
#        children: list["MindMapNode"] = Field(default_factory=list)
# class MeetingResult(BaseModel):
#        title: str
#        objective: str
#        meeting_summary: str
#        tasks_assigned: list[Task]
#        decision_points: list[str]
#        objections: list[str]
#        action_items: list[str]
# # ============================================================
# # QWEN3-27B CLOUD API
# # ============================================================
# def _call_qwen(
#        *,
#        system_prompt: str,
#        user_prompt: str,
#        temperature: float = 0.0,
#        max_tokens: int = QWEN_MAX_OUTPUT_TOKENS,
# ) -> str:
#        """Call the configured Qwen3-27B API."""
#        if not QWEN_API_URL:
#            raise RuntimeError("QWEN_API_URL is not configured.")
#        if not QWEN_API_KEY:
#            raise RuntimeError("QWEN_API_KEY is not configured.")
#        headers = {
#            "Authorization": f"Bearer {QWEN_API_KEY}",
#            "Content-Type": "application/json",
#        }
#        payload = {
#            "model": QWEN_MODEL,
#            "messages": [
#                {
#                    "role": "system",
#                    "content": system_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
#                },
#                {
#                    "role": "user",
#                    "content": user_prompt + "\n\n" + JSON_ONLY_INSTRUCTION,
#                },
#            ],
#            "temperature": temperature,
#            "max_tokens": max_tokens,
#            "context_window": QWEN_CONTEXT_WINDOW,
#        }
#        try:
#            response = requests.post(
#                QWEN_API_URL,
#                headers=headers,
#                json=payload,
#                timeout=300,
#            )
#            response.raise_for_status()
#            data = response.json()
#        except requests.RequestException as exc:
#            raise RuntimeError(
#                f"Qwen API request failed: {exc}"
#            ) from exc
#        except ValueError as exc:
#            raise RuntimeError(
#                "Qwen API returned an invalid HTTP JSON response."
#            ) from exc
#        try:
#            content = data["choices"][0]["message"]["content"]
#        except (KeyError, IndexError, TypeError) as exc:
#            raise RuntimeError(
#                f"Unexpected Qwen API response structure: {data}"
#            ) from exc
#        if not isinstance(content, str) or not content.strip():
#            raise RuntimeError("Qwen API returned an empty response.")
#        return content.strip()
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
#     text = re.sub(r"```(?:json)?[ \t]*", "", text, flags=re.IGNORECASE)
#     return text.replace("```", "").strip()


# def _extract_json_object(text: str, required_keys=None) -> str:
#     """
#     Extract a complete JSON object, preferring an object that matches the schema.
#     If required_keys are provided, never fall back to an unrelated object such
#     as a nested {"task": "..."} object. That fallback caused MeetingResult
#     validation errors for Qwen responses.
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
#                 elif current == "\\\\":
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
#                     candidate_text = text[start:end + 1]
#                     try:
#                         parsed = json.loads(candidate_text)
#                     except json.JSONDecodeError:
#                         break
#                     if isinstance(parsed, dict):
#                         keys_match = (
#                             required_keys is None
#                             or set(required_keys).issubset(parsed.keys())
#                         )
#                         candidates.append(
#                             (keys_match, len(candidate_text), start, candidate_text)
#                         )
#                     break
#     if not candidates:
#         raise ValueError("No complete valid JSON object was found in the model response.")
#     if required_keys is not None:
#         matching = [item for item in candidates if item[0]]
#         if not matching:
#             expected = ", ".join(sorted(required_keys))
#             raise ValueError(
#                 "No JSON object contained all required fields: " + expected
#             )
#         candidates = matching
#     # Prefer the largest matching object, usually the complete outer response.
#     selected = max(candidates, key=lambda item: (item[1], item[2]))
#     return selected[3]
# def _parse_mindmap_json(text: str) -> dict:
#        """Parse and validate the root of a mindmap JSON object."""
#        cleaned = _extract_json_object(
#            text,
#            required_keys={"title", "children"},
#        )
#        parsed = json.loads(cleaned)
#        if not isinstance(parsed, dict):
#            raise ValueError("Mindmap root must be a JSON object.")
#        if not isinstance(parsed.get("title"), str):
#            raise ValueError("Mindmap root must contain a title string.")
#        if not parsed["title"].strip():
#            raise ValueError("Mindmap root title cannot be empty.")
#        if not isinstance(parsed.get("children"), list):
#            raise ValueError("Mindmap children must be a list.")
#        return parsed
# # ============================================================
# # MEETING INTELLIGENCE PROMPT
# # ============================================================
# SYSTEM_PROMPT = """You are MeetMind, an AI meeting intelligence system.
# Analyze the complete meeting transcript and return accurate, professional meeting intelligence grounded in the transcript. The transcript may contain English, Tamil, Tamil-English code-mixed speech, Indian English, informal speech, and ASR errors. Correct an ASR error only when the intended meaning is clear. Speaker diarization is disabled; do not create speaker labels.
# STRICT GROUNDING
# \- Use only information supported by the transcript.
# \- Never invent names, roles, tasks, assignees, deadlines, dates, decisions, objections, action items, milestones, or facts.
# \- Preserve important technical terminology, project names, figures, requirements, constraints, dependencies, and meaningful context.
# \- Clearly distinguish completed work, work in progress, proposals, and future plans.
# \- Do not treat suggestions as confirmed decisions or general discussion as assigned tasks.
# \- Avoid unnecessary duplication between output fields.
# \- Return exactly one valid JSON object with the existing fields and data types. Do not add explanatory text or Markdown code fences outside the JSON.
# TITLE
# Generate a concise, meaningful title describing the actual meeting and its primary subject or project. Do not invent project names. Avoid generic titles when a more informative title can be derived from the transcript.
# OBJECTIVE — COMPULSORY
# Always generate a meaningful, non-empty objective in one concise sentence. Use a second sentence only when necessary.
# \- If the participants explicitly state the meeting purpose, use it.
# \- If the purpose is not explicitly stated, infer the most reasonable objective from the main topic, substantive discussion, project context, and intended outcomes.
# \- If multiple topics are discussed, identify the primary purpose that best represents the meeting.
# \- Do not copy the meeting summary or list individual tasks, decisions, objections, deadlines, or action items.
# \- Never return an empty string, null, or placeholder such as "Unknown", "Not mentioned", or "To discuss various topics".
# \- Keep the objective specific, professional, and grounded in the transcript.
# MEETING_SUMMARY
# Generate a professional, coherent narrative of the substantive meeting discussion. The value of "meeting_summary" MUST be one plain JSON string, never a dictionary, nested object, or array.
# Use plain-text section headings without Markdown heading symbols. Do not use "##", "#", or similar markers before headings. Put each heading on its own line, followed by the paragraph on the next line. Separate sections with a blank line.
# Suitable headings, when relevant, are:
# Meeting Overview
# Detailed Discussion
# Current Status and Progress
# Challenges, Risks, and Concerns
# Conclusion
# Use only headings that add meaningful value to the actual meeting content. Do not force every heading into every summary.
# Required formatting example:
# "Meeting Overview\\\nThe team reviewed the current implementation and discussed the remaining technical challenges.\\\n\\\nDetailed Discussion\\\nThe team examined the integration process and identified areas requiring further validation."
# This example demonstrates the required plain-text heading format only. Generate actual content from the transcript.
# Summary content requirements:
# \- Explain the important topics discussed, relevant technical details, progress reported, challenges raised, and context needed to understand the meeting.
# \- Preserve meaningful names, figures, technical terminology, requirements, and project details.
# \- Distinguish completed work from ongoing activities and future plans.
# \- Write connected, natural paragraphs. Use bullets sparingly and only when they improve readability.
# \- Let the length reflect the complexity and substance of the discussion. Do not impose a fixed word count or sentence count.
# \- Avoid filler, repetition, generic conclusions, and unnecessary verbatim transcript reproduction.
# \- Do not describe the summary template, enumerate its formatting rules, or repeat the same point across multiple sections.
# \- If the meeting discusses a reporting template or summary format, describe that discussion proportionally; do not turn the summary into a long enumeration of the template's requirements unless that is genuinely the meeting's substantive content.
# \- Do not create separate Objective, Tasks Assigned, Decisions, Objections, or Action Items sections inside the summary.
# \- Do not include these headings in meeting_summary: "Decisions and Agreements" or "Action Items and Next Steps". Decisions and actions have separate structured fields.
# \- Mention decisions, tasks, or concerns in the narrative only when necessary to explain the discussion. Leave their full structured details to their dedicated fields.
# \- Omit unsupported sections instead of fabricating content.
# \- Never return the summary headings as JSON keys. All headings and paragraphs must be contained in the single meeting_summary string.
# TASKS_ASSIGNED
# Extract concrete work explicitly assigned to an individual or team or clearly committed to during the meeting. Each task must include a concise task description.
# \- Include "assignee" only when the person's name or responsible team is explicitly stated or clearly identifiable in the transcript.
# \- Include "deadline" only when a deadline or date is explicitly mentioned.
# \- Do not use pronouns such as "I" or "we" as assignees.
# \- If the assignee or deadline is absent, do not invent one and do not display placeholder text such as "Not specified", "N/A", or "Unknown".
# \- Include an expected deliverable only if the existing schema supports it and it is stated or clearly established.
# \- Do not include suggestions or discussion topics that were not assigned.
# \- Return an empty list if no tasks were explicitly assigned.
# \- Preserve the existing task object structure and keys: "task", "assignee", and "deadline". Use null for missing optional values only if required by the existing schema/normalization; never show placeholder text.
# DECISION_POINTS
# Extract significant decisions, approvals, rejections, and agreements actually reached during the meeting.
# \- State what was decided and include relevant rationale or conditions only when supported.
# \- Distinguish confirmed decisions from proposals, suggestions, assumptions, and unresolved questions.
# \- Do not invent decisions or duplicate the full narrative.
# \- Represent decisions as strings, matching the existing schema.
# \- Return an empty list if no explicit decisions were reached.
# OBJECTIONS
# Identify genuine objections, disagreements, reservations, blockers, risks, or concerns explicitly raised during the meeting.
# \- Describe the concern accurately and include its reason, impact, or proposed resolution only when mentioned.
# \- Distinguish unresolved concerns from concerns that were addressed or resolved.
# \- Do not interpret ordinary discussion as disagreement without evidence.
# \- Represent objections as strings, matching the existing schema.
# \- Return an empty list if no substantive objections or concerns were raised.
# ACTION_ITEMS
# Extract concrete follow-up actions explicitly agreed to or clearly committed to during the meeting.
# \- Represent each action item as a concise string, matching the existing schema.
# \- Do not turn every suggestion or discussion point into an action item.
# \- Do not list completed work as a future action.
# \- Do not invent ownership, deadlines, or commitments.
# \- Avoid duplicating tasks_assigned unnecessarily.
# \- Return an empty list if no follow-up actions were identified.
# FINAL VALIDATION
# Before returning the JSON, verify that:
# 1\. All required fields are present: "title", "objective", "meeting_summary", "tasks_assigned", "decision_points", "objections", and "action_items".
# 2\. Every field uses the data type required by the existing schema.
# 3\. "objective" is a meaningful, non-empty string.
# 4\. "meeting_summary" is one string with plain-text headings and paragraphs; it is not an object or array.
# 5\. Summary headings do not begin with "##" or "#".
# 6\. "meeting_summary" contains neither "Decisions and Agreements" nor "Action Items and Next Steps" as headings.
# 7\. The summary does not repeat the objective or reproduce the structured task, decision, objection, or action-item lists.
# 8\. Missing assignees and deadlines are not invented and no placeholder labels are generated.
# 9\. Every claim is supported by the transcript.
# 10\. The response is valid JSON with no text outside the JSON object."""
# # ============================================================
# # MEETING SUMMARY GENERATION
# # ============================================================
# def _normalize_meeting_result_data(data: dict) -> dict:
#        """Normalize LLM meeting output to the MeetingResult schema."""
#        if not isinstance(data, dict):
#            raise ValueError("Meeting result must be a JSON object.")
#        normalized = dict(data)
#        action_items = normalized.get("action_items", [])
#        if not isinstance(action_items, list):
#            action_items = []
#        normalized["action_items"] = []
#        for item in action_items:
#            if isinstance(item, str) and item.strip():
#                normalized["action_items"].append(item.strip())
#            elif isinstance(item, dict):
#                text = item.get("action") or item.get("task") or item.get("description") or item.get("action_item")
#                if isinstance(text, str) and text.strip():
#                    normalized["action_items"].append(text.strip())
#        decision_points = normalized.get("decision_points", [])
#        if not isinstance(decision_points, list):
#            decision_points = []
#        normalized["decision_points"] = []
#        for item in decision_points:
#            if isinstance(item, str) and item.strip():
#                normalized["decision_points"].append(item.strip())
#            elif isinstance(item, dict):
#                text = item.get("decision") or item.get("description") or item.get("text")
#                if isinstance(text, str) and text.strip():
#                    normalized["decision_points"].append(text.strip())
#        objections = normalized.get("objections", [])
#        if not isinstance(objections, list):
#            objections = []
#        normalized["objections"] = []
#        for item in objections:
#            if isinstance(item, str) and item.strip():
#                normalized["objections"].append(item.strip())
#            elif isinstance(item, dict):
#                text = item.get("objection") or item.get("concern") or item.get("description") or item.get("text")
#                if isinstance(text, str) and text.strip():
#                    normalized["objections"].append(text.strip())
#        tasks = normalized.get("tasks_assigned", [])
#        if not isinstance(tasks, list):
#            tasks = []
#        normalized_tasks = []
#        for item in tasks:
#            if isinstance(item, dict):
#                task = item.get("task") or item.get("action") or item.get("description")
#                if isinstance(task, str) and task.strip():
#                    normalized_tasks.append({
#                        "task": task.strip(),
#                        "assignee": item.get("assignee"),
#                        "deadline": item.get("deadline"),
#                    })
#            elif isinstance(item, str) and item.strip():
#                normalized_tasks.append({"task": item.strip(), "assignee": None, "deadline": None})
#        # Normalize each deadline explicitly, then remove years from any other
#        # recognizable dates in summaries, decisions, objections, and action items.
#        for task_item in normalized_tasks:
#            task_item["deadline"] = format_deadline(task_item.get("deadline"))
#        normalized["tasks_assigned"] = normalized_tasks
#        normalized = _normalize_dates_recursively(normalized)
#        return normalized
# def generate_meeting_summary(
#     transcript: str,
#     _llm_call=call_mistral,
#     _llm_model=MISTRAL_MODEL,
# ):
#     """
#     Generate and validate meeting intelligence.
#     If the model returns malformed JSON or the wrong schema, make one repair
#     request using the same model. Mind-map generation remains independent.
#     """
#     transcript = (transcript or "").strip()
#     if not transcript:
#         raise ValueError("Cannot generate a summary from an empty transcript.")
#     required_keys = {
#         "title",
#         "objective",
#         "meeting_summary",
#         "tasks_assigned",
#         "decision_points",
#         "objections",
#         "action_items",
#     }
#     user_prompt = f"""
# Analyze the COMPLETE meeting transcript.
# IMPORTANT:
# \- "objective" is compulsory and must be a meaningful, non-empty string.
# \- "meeting_summary" must be one string containing plain-text headings and
#   paragraphs. Do not return it as a nested JSON object or dictionary.
# \- Do not use Markdown heading markers such as # or ##.
# \- Use the existing schema and exactly these top-level fields:
#   title, objective, meeting_summary, tasks_assigned, decision_points,
#   objections, action_items.
# \- tasks_assigned must be a list of objects with task, assignee, deadline.
# \- Use empty lists when no relevant items exist.
# \- Do not invent names, tasks, assignees, dates, deadlines, decisions, or facts.
# \- Preserve transcript-grounding and the existing summary formatting rules.
# \- Do not put "Decisions and Agreements" or "Action Items and Next Steps"
#   as headings inside meeting_summary.
# Return one JSON object in this shape:
# {{
#   "title": "Meeting title",
#   "objective": "Purpose of the meeting",
#   "meeting_summary": "Meeting Overview\\\n...\\\n\\\nDetailed Discussion\\\n...",
#   "tasks_assigned": [
#     {{"task": "Task description", "assignee": null, "deadline": null}}
#   ],
#   "decision_points": [],
#   "objections": [],
#   "action_items": []
# }}
# COMPLETE MEETING TRANSCRIPT:
# ============================
# {transcript}
# ============================
# Return only the JSON object.
# """
#     def parse_and_validate(raw_content: str):
#         cleaned = _extract_json_object(
#             raw_content,
#             required_keys=required_keys,
#         )
#         data = json.loads(cleaned)
#         if not isinstance(data.get("meeting_summary"), str):
#             raise ValueError(
#                 "'meeting_summary' must be a single string, not a nested object or list."
#             )
#         if not isinstance(data.get("objective"), str) or not data["objective"].strip():
#             raise ValueError("'objective' must be a meaningful, non-empty string.")
#         if not isinstance(data.get("title"), str) or not data["title"].strip():
#             raise ValueError("'title' must be a non-empty string.")
#         data = _normalize_meeting_result_data(data)
#         result = MeetingResult.model_validate(data)
#         if not result.meeting_summary.strip():
#             raise ValueError("'meeting_summary' cannot be empty.")
#         if not result.objective.strip():
#             raise ValueError("'objective' cannot be empty.")
#         return result
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
#         raise RuntimeError(f"{_llm_model} returned an empty meeting summary.")
#     try:
#         result = parse_and_validate(content)
#         return result.model_dump()
#     except Exception as first_error:
#         # Retry only schema/JSON failures. Keep the original transcript and
#         # ask the same model to repair its own output without adding facts.
#         repair_prompt = f"""
# The previous response did not match the required meeting-result JSON schema.
# Validation error:
# {first_error}
# Repair the response using the COMPLETE meeting transcript below as the source
# of truth. Do not invent information. Return exactly one valid JSON object with
# all seven top-level fields:
# title, objective, meeting_summary, tasks_assigned, decision_points,
# objections, action_items.
# Requirements:
# \- objective must be a meaningful, non-empty string.
# \- meeting_summary must be one plain string with headings and paragraphs,
#   never an object, dictionary, array, or nested JSON.
# \- tasks_assigned must be a list of objects containing task, assignee, deadline.
# \- decision_points, objections, and action_items must be lists of strings.
# \- Use [] when no relevant items exist.
# \- Do not include reasoning, Markdown fences, or explanatory text.
# \- Do not add unsupported facts.
# INVALID PREVIOUS RESPONSE:
# {content}
# COMPLETE MEETING TRANSCRIPT:
# ============================
# {transcript}
# ============================
# Return only the corrected JSON object.
# """
#         try:
#             repaired_content = _llm_call(
#                 system_prompt=(
#                     SYSTEM_PROMPT
#                     + "\n\nYou are repairing a schema-invalid response. "
#                     "Return only one valid JSON object matching the exact schema."
#                 ),
#                 user_prompt=repair_prompt,
#                 temperature=0.0,
#                 max_tokens=4096,
#             )
#             if not isinstance(repaired_content, str) or not repaired_content.strip():
#                 raise ValueError("The repair response was empty.")
#             result = parse_and_validate(repaired_content)
#             return result.model_dump()
#         except Exception as repair_error:
#             raise RuntimeError(
#                 f"{_llm_model} returned invalid structured meeting output after "
#                 f"one automatic repair attempt. Original error: {first_error}. "
#                 f"Repair error: {repair_error}"
#             ) from repair_error
# # MINDMAP VALIDATION
# # ============================================================
# def _clean_mindmap_node(node: dict) -> dict:
#        """Recursively validate and normalize mindmap nodes."""
#        if not isinstance(node, dict):
#            raise ValueError("Every mindmap node must be an object.")
#        title = node.get("title")
#        if not isinstance(title, str) or not title.strip():
#            raise ValueError("Every mindmap node must have a non-empty title.")
#        children = node.get("children", [])
#        if not isinstance(children, list):
#            raise ValueError(
#                f"Children for node {title!r} must be a list."
#            )
#        cleaned = {
#            "title": _normalize_dates_in_text(title.strip()),
#            "children": [
#                _clean_mindmap_node(child)
#                for child in children
#            ],
#        }
#        return cleaned
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
# \- title: a string
# \- children: an array of child nodes, which may be empty
# Return exactly one JSON object with a root title and children.
# Do not add any other fields.
# Do not return reasoning, Markdown, introductions, or explanations.
# """
# def generate_mindmap(
#        transcript: str,
#        _llm_call=call_mistral,
#        _llm_model=MISTRAL_MODEL,
# ):
#        """Generate a hierarchical mindmap directly from the transcript."""
#        transcript = (transcript or "").strip()
#        if not transcript:
#            raise ValueError(
#                "Cannot generate a mindmap because the transcript is empty."
#            )
#        user_prompt = f"""
# Analyze the complete meeting transcript and create a hierarchical mindmap.
# Capture relevant:
# \- Main topics
# \- Technical discussions
# \- Current status
# \- Problems or challenges
# \- Decisions
# \- Action items
# \- Tasks
# \- Explicit timelines
# \- Next steps
# Only include categories supported by the transcript.
# Return exactly this structure:
# {{
#      "title": "Main Meeting Topic",
#      "children": [
#        {{
#          "title": "Major Topic",
#          "children": [
#            {{
#              "title": "Important Detail",
#              "children": []
#            }}
#          ]
#        }}
#      ]
# }}
# Every node must contain a title and a children array.
# Do not include fields other than title and children.
# COMPLETE MEETING TRANSCRIPT:
# \\\\\\\============================
# {transcript}
# \\\\\\\============================
# Return only one valid JSON object.
# """
#        try:
#            content = _llm_call(
#                system_prompt=MINDMAP_SYSTEM_PROMPT,
#                user_prompt=user_prompt,
#                temperature=0.0,
#                max_tokens=4096,
#            )
#        except Exception as exc:
#            raise RuntimeError(
#                f"Mindmap generation failed for {_llm_model}: {exc}"
#            ) from exc
#        if not isinstance(content, str) or not content.strip():
#            raise RuntimeError(
#                f"{_llm_model} returned an empty mindmap response."
#            )
#        try:
#            mindmap_data = _parse_mindmap_json(content)
#        except Exception as first_error:
#            repair_prompt = f"""
# Repair the following malformed mindmap response.
# Requirements:
# \- Preserve the existing information.
# \- Do not invent new content.
# \- Return one valid JSON object.
# \- The root must contain title and children.
# \- Every node must contain title and children.
# \- Use only title and children fields.
# \- Do not include reasoning, Markdown, or explanations.
# Malformed response:
# {content}
# Return only the repaired JSON object.
# """
#            try:
#                repaired_content = _llm_call(
#                    system_prompt=(
#                        "You are a JSON repair engine. Return only one valid "
#                        "mindmap JSON object. Do not explain anything."
#                    ),
#                    user_prompt=repair_prompt,
#                    temperature=0.0,
#                    max_tokens=4096,
#                )
#                mindmap_data = _parse_mindmap_json(repaired_content)
#            except Exception as repair_error:
#                raise RuntimeError(
#                    f"{_llm_model} returned invalid mindmap JSON, and "
#                    f"automatic repair failed. Original error: {first_error}. "
#                    f"Repair error: {repair_error}"
#                ) from repair_error
#        try:
#            return _clean_mindmap_node(mindmap_data)
#        except Exception as exc:
#            raise RuntimeError(
#                f"{_llm_model} returned an invalid mindmap structure: {exc}"
#            ) from exc
# # ============================================================
# # QWEN3-27B WRAPPERS
# # ============================================================
# def generate_meeting_summary_qwen(transcript: str):
#        """Generate meeting intelligence using Qwen3-27B Cloud API."""
#        return generate_meeting_summary(
#            transcript,
#            _llm_call=_call_qwen,
#            _llm_model=QWEN_MODEL,
#        )
# def generate_mindmap_qwen(transcript: str):
#        """Generate a mindmap using Qwen3-27B Cloud API."""
#        return generate_mindmap(
#            transcript,
#            _llm_call=_call_qwen,
#            _llm_model=QWEN_MODEL,
#        )

"""MeetMind - Meeting Intelligence
Mistral 128B API and Qwen3-27B API
Meeting summary, tasks, decisions, action items, and hierarchical mindmap.
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
# DATE NORMALIZATION
# ============================================================
_MONTHS = (
    "January February March April May June July August September "
    "October November December"
).split()
_MONTH_PATTERN = "|".join(_MONTHS)
def format_deadline(value):
    """
    Normalize a date/deadline for display without a year.
    Examples:
      2023-10-17 -> October 17
      October 17th, 2023 -> October 17
      17 October 2023 -> October 17
      October 17 -> October 17
    Does not invent or infer a date. If a value cannot safely be recognized
    as a date, it is returned unchanged except for surrounding whitespace.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text:
        return None
    # ISO date or ISO datetime. Keep the actual month/day; drop the year.
    match = re.fullmatch(
        r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[Tt ].*)?", text
    )
    if match:
        month, day = int(match.group(2)), int(match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{_MONTHS[month - 1]} {day}"
    # Month DD[st/nd/rd/th][, YYYY] or Month DD, YYYY
    match = re.fullmatch(
        rf"({_MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:,?\s+\d{{4}})?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        month_name = next(m for m in _MONTHS if m.lower() == match.group(1).lower())
        day = int(match.group(2))
        if 1 <= day <= 31:
            return f"{month_name} {day}"
    # DD Month [YYYY]
    match = re.fullmatch(
        rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})(?:,?\s+\d{{4}})?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        day = int(match.group(1))
        month_name = next(m for m in _MONTHS if m.lower() == match.group(2).lower())
        if 1 <= day <= 31:
            return f"{month_name} {day}"
    return text
def _normalize_dates_in_text(value):
    """Remove years from recognizable dates embedded in report text."""
    if not isinstance(value, str) or not value:
        return value
    # Convert ISO dates/datetimes anywhere in a string.
    value = re.sub(
        r"\b\d{4}-\d{1,2}-\d{1,2}(?:[Tt ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b",
        lambda m: format_deadline(m.group(0)),
        value,
    )
    # Convert month-first dates with ordinal suffix and optional year.
    value = re.sub(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}})(st|nd|rd|th)?"
        rf"(,?\s+\d{{4}})?\b",
        lambda m: format_deadline(m.group(1) + " " + m.group(2)),
        value,
        flags=re.IGNORECASE,
    )
    # Convert day-first dates with optional year.
    value = re.sub(
        rf"\b(\d{{1,2}})(st|nd|rd|th)?\s+({_MONTH_PATTERN})(,?\s+\d{{4}})?\b",
        lambda m: format_deadline(m.group(1) + " " + m.group(3)),
        value,
        flags=re.IGNORECASE,
    )
    return value
def _normalize_dates_recursively(value):
    """Normalize date strings throughout summary data and mindmap nodes."""
    if isinstance(value, str):
        return _normalize_dates_in_text(value)
    if isinstance(value, list):
        return [_normalize_dates_recursively(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_dates_recursively(item) for key, item in value.items()}
    return value
# ============================================================
# PYDANTIC SCHEMAS
# ============================================================
class Task(BaseModel):
       task: str
       assignee: Optional[str] = None
       deadline: Optional[str] = None
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
        r"\<think\b[^>]*>.*?\</think\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\<think\b[^>]*>.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"```(?:json)?[ **\t**]*", "", text, flags=re.IGNORECASE)
    return text.replace("```", "").strip()
def _extract_json_object(text: str, required_keys=None) -> str:
    """
    Extract a complete JSON object, preferring an object that matches the schema.
    If required_keys are provided, never fall back to an unrelated object such
    as a nested {"task": "..."} object. That fallback caused MeetingResult
    validation errors for Qwen responses.
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
                elif current == "\\":
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
                    candidate_text = text[start:end + 1]
                    try:
                        parsed = json.loads(candidate_text)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        keys_match = (
                            required_keys is None
                            or set(required_keys).issubset(parsed.keys())
                        )
                        candidates.append(
                            (keys_match, len(candidate_text), start, candidate_text)
                        )
                    break
    if not candidates:
        raise ValueError("No complete valid JSON object was found in the model response.")
    if required_keys is not None:
        matching = [item for item in candidates if item[0]]
        if not matching:
            expected = ", ".join(sorted(required_keys))
            raise ValueError(
                "No JSON object contained all required fields: " + expected
            )
        candidates = matching
    # Prefer the largest matching object, usually the complete outer response.
    selected = max(candidates, key=lambda item: (item[1], item[2]))
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
SYSTEM_PROMPT = """You are Vidatha, an AI meeting intelligence system.
Analyze the complete meeting transcript and return accurate, professional meeting intelligence grounded in the transcript. The transcript may contain English, Tamil, Tamil-English code-mixed speech, Indian English, informal speech, and ASR errors. Correct an ASR error only when the intended meaning is clear. Speaker diarization is disabled; do not create speaker labels.
STRICT GROUNDING
- Use only information supported by the transcript.
- Never invent names, roles, tasks, assignees, deadlines, dates, decisions, objections, action items, milestones, or facts.
- Preserve important technical terminology, project names, figures, requirements, constraints, dependencies, and meaningful context.
- Clearly distinguish completed work, work in progress, proposals, and future plans.
- Do not treat suggestions as confirmed decisions or general discussion as assigned tasks.
- Avoid unnecessary duplication between output fields.
- Return exactly one valid JSON object with the existing fields and data types. Do not add explanatory text or Markdown code fences outside the JSON.
TITLE
Generate a concise, meaningful title describing the actual meeting and its primary subject or project. Do not invent project names. Avoid generic titles when a more informative title can be derived from the transcript.
OBJECTIVE — COMPULSORY
Always generate a meaningful, non-empty objective in one concise sentence. Use a second sentence only when necessary.
- If the participants explicitly state the meeting purpose, use it.
- If the purpose is not explicitly stated, infer the most reasonable objective from the main topic, substantive discussion, project context, and intended outcomes.
- If multiple topics are discussed, identify the primary purpose that best represents the meeting.
- Do not copy the meeting summary or list individual tasks, decisions, objections, deadlines, or action items.
- Never return an empty string, null, or placeholder such as "Unknown", "Not mentioned", or "To discuss various topics".
- Keep the objective specific, professional, and grounded in the transcript.
MEETING_SUMMARY
Generate a professional, coherent narrative of the substantive meeting discussion. The value of "meeting_summary" MUST be one plain JSON string, never a dictionary, nested object, or array.
Use plain-text section headings without Markdown heading symbols. Do not use "##", "#", or similar markers before headings. Put each heading on its own line, followed by the paragraph on the next line. Separate sections with a blank line.
Suitable headings, when relevant, are:
Meeting Overview
Detailed Discussion
Current Status and Progress
Challenges, Risks, and Concerns
Conclusion
Use only headings that add meaningful value to the actual meeting content. Do not force every heading into every summary.
Required formatting example:
"Meeting Overview\\\nThe team reviewed the current implementation and discussed the remaining technical challenges.\\\n\\\nDetailed Discussion\\\nThe team examined the integration process and identified areas requiring further validation."
This example demonstrates the required plain-text heading format only. Generate actual content from the transcript.
Summary content requirements:
- Explain the important topics discussed, relevant technical details, progress reported, challenges raised, and context needed to understand the meeting.
- Preserve meaningful names, figures, technical terminology, requirements, and project details.
- Distinguish completed work from ongoing activities and future plans.
- Write connected, natural paragraphs. Use bullets sparingly and only when they improve readability.
- Let the length reflect the complexity and substance of the discussion. Do not impose a fixed word count or sentence count.
- Avoid filler, repetition, generic conclusions, and unnecessary verbatim transcript reproduction.
- Do not describe the summary template, enumerate its formatting rules, or repeat the same point across multiple sections.
- If the meeting discusses a reporting template or summary format, describe that discussion proportionally; do not turn the summary into a long enumeration of the template's requirements unless that is genuinely the meeting's substantive content.
- Do not create separate Objective, Tasks Assigned, Decisions, Objections, or Action Items sections inside the summary.
- Do not include these headings in meeting_summary: "Decisions and Agreements" or "Action Items and Next Steps". Decisions and actions have separate structured fields.
- Mention decisions, tasks, or concerns in the narrative only when necessary to explain the discussion. Leave their full structured details to their dedicated fields.
- Omit unsupported sections instead of fabricating content.
- Never return the summary headings as JSON keys. All headings and paragraphs must be contained in the single meeting_summary string.
TASKS_ASSIGNED
Extract concrete work explicitly assigned to an individual or team or clearly committed to during the meeting. Each task must include a concise task description.
- Include "assignee" only when the person's name or responsible team is explicitly stated or clearly identifiable in the transcript.
- Include "deadline" only when a deadline or date is explicitly mentioned.
- Do not use pronouns such as "I" or "we" as assignees.
- If the assignee or deadline is absent, do not invent one and do not display placeholder text such as "Not specified", "N/A", or "Unknown".
- Include an expected deliverable only if the existing schema supports it and it is stated or clearly established.
- Do not include suggestions or discussion topics that were not assigned.
- Return an empty list if no tasks were explicitly assigned.
- Preserve the existing task object structure and keys: "task", "assignee", and "deadline". Use null for missing optional values only if required by the existing schema/normalization; never show placeholder text.
DECISION_POINTS
Extract significant decisions, approvals, rejections, and agreements actually reached during the meeting.
- State what was decided and include relevant rationale or conditions only when supported.
- Distinguish confirmed decisions from proposals, suggestions, assumptions, and unresolved questions.
- Do not invent decisions or duplicate the full narrative.
- Represent decisions as strings, matching the existing schema.
- Return an empty list if no explicit decisions were reached.
OBJECTIONS
Identify genuine objections, disagreements, reservations, blockers, risks, or concerns explicitly raised during the meeting.
- Describe the concern accurately and include its reason, impact, or proposed resolution only when mentioned.
- Distinguish unresolved concerns from concerns that were addressed or resolved.
- Do not interpret ordinary discussion as disagreement without evidence.
- Represent objections as strings, matching the existing schema.
- Return an empty list if no substantive objections or concerns were raised.
ACTION_ITEMS
Extract concrete follow-up actions explicitly agreed to or clearly committed to during the meeting.
- Represent each action item as a concise string, matching the existing schema.
- Do not turn every suggestion or discussion point into an action item.
- Do not list completed work as a future action.
- Do not invent ownership, deadlines, or commitments.
- Avoid duplicating tasks_assigned unnecessarily.
- Return an empty list if no follow-up actions were identified.
FINAL VALIDATION
Before returning the JSON, verify that:
1\. All required fields are present: "title", "objective", "meeting_summary", "tasks_assigned", "decision_points", "objections", and "action_items".
2\. Every field uses the data type required by the existing schema.
3\. "objective" is a meaningful, non-empty string.
4\. "meeting_summary" is one string with plain-text headings and paragraphs; it is not an object or array.
5\. Summary headings do not begin with "##" or "#".
6\. "meeting_summary" contains neither "Decisions and Agreements" nor "Action Items and Next Steps" as headings.
7\. The summary does not repeat the objective or reproduce the structured task, decision, objection, or action-item lists.
8\. Missing assignees and deadlines are not invented and no placeholder labels are generated.
9\. Every claim is supported by the transcript.
10\. The response is valid JSON with no text outside the JSON object."""
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
       # Normalize each deadline explicitly, then remove years from any other
       # recognizable dates in summaries, decisions, objections, and action items.
       for task_item in normalized_tasks:
           task_item["deadline"] = format_deadline(task_item.get("deadline"))
       normalized["tasks_assigned"] = normalized_tasks
       normalized = _normalize_dates_recursively(normalized)
       return normalized
def generate_meeting_summary(
    transcript: str,
    _llm_call=call_mistral,
    _llm_model=MISTRAL_MODEL,
):
    """
    Generate and validate meeting intelligence.
    If the model returns malformed JSON or the wrong schema, make one repair
    request using the same model. Mind-map generation remains independent.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Cannot generate a summary from an empty transcript.")
    required_keys = {
        "title",
        "objective",
        "meeting_summary",
        "tasks_assigned",
        "decision_points",
        "objections",
        "action_items",
    }
    user_prompt = f"""
Analyze the COMPLETE meeting transcript.
IMPORTANT:
- "objective" is compulsory and must be a meaningful, non-empty string.
- "meeting_summary" must be one string containing plain-text headings and
  paragraphs. Do not return it as a nested JSON object or dictionary.
- Do not use Markdown heading markers such as # or ##.
- Use the existing schema and exactly these top-level fields:
  title, objective, meeting_summary, tasks_assigned, decision_points,
  objections, action_items.
- tasks_assigned must be a list of objects with task, assignee, deadline.
- Use empty lists when no relevant items exist.
- Do not invent names, tasks, assignees, dates, deadlines, decisions, or facts.
- Preserve transcript-grounding and the existing summary formatting rules.
- Do not put "Decisions and Agreements" or "Action Items and Next Steps"
  as headings inside meeting_summary.
Return one JSON object in this shape:
{{
  "title": "Meeting title",
  "objective": "Purpose of the meeting",
  "meeting_summary": "Meeting Overview\\\n...\\\n\\\nDetailed Discussion\\\n...",
  "tasks_assigned": [
    {{"task": "Task description", "assignee": null, "deadline": null}}
  ],
  "decision_points": [],
  "objections": [],
  "action_items": []
}}
COMPLETE MEETING TRANSCRIPT:
============================
{transcript}
============================
Return only the JSON object.
"""
    def parse_and_validate(raw_content: str):
        cleaned = _extract_json_object(
            raw_content,
            required_keys=required_keys,
        )
        data = json.loads(cleaned)
        if not isinstance(data.get("meeting_summary"), str):
            raise ValueError(
                "'meeting_summary' must be a single string, not a nested object or list."
            )
        if not isinstance(data.get("objective"), str) or not data["objective"].strip():
            raise ValueError("'objective' must be a meaningful, non-empty string.")
        if not isinstance(data.get("title"), str) or not data["title"].strip():
            raise ValueError("'title' must be a non-empty string.")
        data = _normalize_meeting_result_data(data)
        result = MeetingResult.model_validate(data)
        if not result.meeting_summary.strip():
            raise ValueError("'meeting_summary' cannot be empty.")
        if not result.objective.strip():
            raise ValueError("'objective' cannot be empty.")
        return result
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
        raise RuntimeError(f"{_llm_model} returned an empty meeting summary.")
    try:
        result = parse_and_validate(content)
        return result.model_dump()
    except Exception as first_error:
        # Retry only schema/JSON failures. Keep the original transcript and
        # ask the same model to repair its own output without adding facts.
        repair_prompt = f"""
The previous response did not match the required meeting-result JSON schema.
Validation error:
{first_error}
Repair the response using the COMPLETE meeting transcript below as the source
of truth. Do not invent information. Return exactly one valid JSON object with
all seven top-level fields:
title, objective, meeting_summary, tasks_assigned, decision_points,
objections, action_items.
Requirements:
- objective must be a meaningful, non-empty string.
- meeting_summary must be one plain string with headings and paragraphs,
  never an object, dictionary, array, or nested JSON.
- tasks_assigned must be a list of objects containing task, assignee, deadline.
- decision_points, objections, and action_items must be lists of strings.
- Use [] when no relevant items exist.
- Do not include reasoning, Markdown fences, or explanatory text.
- Do not add unsupported facts.
INVALID PREVIOUS RESPONSE:
{content}
COMPLETE MEETING TRANSCRIPT:
============================
{transcript}
============================
Return only the corrected JSON object.
"""
        try:
            repaired_content = _llm_call(
                system_prompt=(
                    SYSTEM_PROMPT
                    + "\n\nYou are repairing a schema-invalid response. "
                    "Return only one valid JSON object matching the exact schema."
                ),
                user_prompt=repair_prompt,
                temperature=0.0,
                max_tokens=4096,
            )
            if not isinstance(repaired_content, str) or not repaired_content.strip():
                raise ValueError("The repair response was empty.")
            result = parse_and_validate(repaired_content)
            return result.model_dump()
        except Exception as repair_error:
            raise RuntimeError(
                f"{_llm_model} returned invalid structured meeting output after "
                f"one automatic repair attempt. Original error: {first_error}. "
                f"Repair error: {repair_error}"
            ) from repair_error
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
           "title": _normalize_dates_in_text(title.strip()),
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
You are Vidatha, a meeting mindmap generator.
Generate a hierarchical mindmap directly from the complete transcript.
Do not generate the mindmap from a summary.
Use only information supported by the transcript.
Do not invent names, decisions, tasks, deadlines, or facts.
Keep node titles concise and meaningful.
Every node must contain:
- title: a string
- children: an array of child nodes, which may be empty
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
- Main topics
- Technical discussions
- Current status
- Problems or challenges
- Decisions
- Action items
- Tasks
- Explicit timelines
- Next steps
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
\\\\\\\============================
{transcript}
\\\\\\\============================
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
- Preserve the existing information.
- Do not invent new content.
- Return one valid JSON object.
- The root must contain title and children.
- Every node must contain title and children.
- Use only title and children fields.
- Do not include reasoning, Markdown, or explanations.
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


# ============================================================
# DOCTOR PRESCRIPTION TEMPLATE (ADDITIVE; MOM FUNCTIONS UNCHANGED)
# ============================================================

DOCTOR_PRESCRIPTION_SYSTEM_PROMPT = """You are Vidatha's clinical documentation assistant.
Extract a DRAFT doctor-visit prescription form from the supplied consultation transcript.
This is documentation assistance only, not medical decision-making.
STRICT SAFETY AND GROUNDING:
- Use only clinical details explicitly supported by the transcript.
- Never invent or recommend a diagnosis, medicine, dosage, route, frequency, duration,
  investigation, vital sign, allergy, warning sign, or follow-up date.
- If a value is absent or unclear, return an empty string. Do not infer from age, symptoms,
  common practice, or general medical knowledge.
- Preserve uncertainty and use the transcript's own terminology where appropriate.
- Do not transform a possible diagnosis into a confirmed diagnosis.
- Medicine entries must only reproduce medicines and instructions explicitly stated in the transcript.
- Return exactly one valid JSON object matching the requested fields, with no Markdown or explanation.
"""

DOCTOR_PRESCRIPTION_FIELDS = {
    "patient_name": "",
    "age_sex": "",
    "visit_date": "",
    "doctor_name": "",
    "chief_complaint": "",
    "symptoms_history": "",
    "allergies": "",
    "temperature": "",
    "blood_pressure": "",
    "pulse_rate": "",
    "spo2": "",
    "examination_findings": "",
    "diagnosis": "",
    "medicines": [],
    "tests_advised": "",
    "advice": "",
    "warning_signs": "",
    "next_visit": "",
}


def _normalize_doctor_prescription(data: dict) -> dict:
    """Return only the known prescription fields, without fabricating values."""
    if not isinstance(data, dict):
        raise ValueError("Prescription output must be a JSON object.")
    normalized = dict(DOCTOR_PRESCRIPTION_FIELDS)
    text_fields = [key for key in normalized if key != "medicines"]
    for key in text_fields:
        value = data.get(key, "")
        normalized[key] = value.strip() if isinstance(value, str) else ""
    medicines = data.get("medicines", [])
    if isinstance(medicines, list):
        for item in medicines:
            if not isinstance(item, dict):
                continue
            medicine = {
                field: (item.get(field, "").strip() if isinstance(item.get(field, ""), str) else "")
                for field in ("medicine", "dose", "route", "frequency", "duration", "instructions")
            }
            # Do not add completely empty medicine rows.
            if any(medicine.values()):
                normalized["medicines"].append(medicine)
    # Keep visit_date in ISO format because the frontend uses an HTML date input.
    visit_date = normalized.get("visit_date", "")
    normalized = _normalize_dates_recursively(normalized)
    normalized["visit_date"] = visit_date
    return normalized


def generate_doctor_prescription(
    transcript: str,
    _llm_call=call_mistral,
    _llm_model=MISTRAL_MODEL,
):
    """Extract a clinician-review draft; separate from MOM summary and mindmap logic."""
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Cannot generate a prescription draft from an empty transcript.")

    fields = list(DOCTOR_PRESCRIPTION_FIELDS.keys())
    example = dict(DOCTOR_PRESCRIPTION_FIELDS)
    example["medicines"] = [{
        "medicine": "", "dose": "", "route": "", "frequency": "",
        "duration": "", "instructions": ""
    }]
    user_prompt = f"""Extract the consultation details into this exact JSON shape.
For fields not stated in the transcript, use an empty string. For medicines, use an empty
array when none were explicitly mentioned. Do not create clinical content to fill blanks.
Field-specific extraction rules:
- chief_complaint: capture the main symptoms and stated duration.
- symptoms_history: include associated symptoms, relevant negatives, and explicitly stated
  travel/contact history. Keep patient-reported facts distinct from clinician observations.
- allergies: record the patient's stated allergy status verbatim in concise wording; e.g. if
  the patient says they have no drug allergies, use "No known drug allergies (patient-reported)".
- temperature: preserve the value and whether it was reported by the patient or measured now.
- examination_findings and unreported vital signs: leave blank unless actual findings/values
  were stated. A plan to check vitals is not an examination result.
- diagnosis: leave blank unless a diagnosis was actually stated by the clinician.
- medicines: include only medicines and directions explicitly prescribed in the transcript;
  symptoms alone are not a basis for suggesting medication.
- tests_advised: only list tests as ordered/advised if definite; if merely conditional or possible,
  leave blank rather than presenting it as an order.
- advice and warning_signs: capture advice and red flags explicitly stated in the transcript.
- next_visit: capture a clearly stated follow-up interval and any earlier-return instruction.
All top-level keys are required: {', '.join(fields)}.
The medicines array may contain objects with exactly these keys: medicine, dose, route,
frequency, duration, instructions.
Return only the JSON object.

Required shape:
{json.dumps(example, ensure_ascii=False, indent=2)}

CONSULTATION TRANSCRIPT:
========================
{transcript}
========================
"""

    try:
        content = _llm_call(
            system_prompt=DOCTOR_PRESCRIPTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )
        cleaned = _extract_json_object(content, required_keys=set(fields))
        return _normalize_doctor_prescription(json.loads(cleaned))
    except Exception as first_error:
        repair_prompt = f"""Repair the following response into one valid JSON object with
exactly these top-level keys: {', '.join(fields)}. Keep only information already present;
do not invent or add clinical details. Missing text fields must be empty strings and missing
medicines must be an empty array. Each medicine object may contain only medicine, dose, route,
frequency, duration, instructions.

Validation error: {first_error}
Invalid response:
{locals().get('content', '')}

Original transcript:
{transcript}
Return only the JSON object."""
        try:
            repaired = _llm_call(
                system_prompt=DOCTOR_PRESCRIPTION_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                temperature=0.0,
                max_tokens=4096,
            )
            cleaned = _extract_json_object(repaired, required_keys=set(fields))
            return _normalize_doctor_prescription(json.loads(cleaned))
        except Exception as repair_error:
            raise RuntimeError(
                f"{_llm_model} returned invalid doctor-prescription output after repair. "
                f"Original error: {first_error}. Repair error: {repair_error}"
            ) from repair_error


def generate_doctor_prescription_qwen(transcript: str):
    """Generate a clinician-review prescription draft with the Qwen API."""
    return generate_doctor_prescription(
        transcript,
        _llm_call=_call_qwen,
        _llm_model=QWEN_MODEL,
    )
