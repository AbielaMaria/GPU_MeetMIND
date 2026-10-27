"""
MeetMind Interview template — evaluation with BharatAI Qwen3-27B.

Independent of the MOM summary / mind-map / prescription pipeline
(meeting_intelligence.py): it talks to the BharatAI OpenAI-compatible
gateway directly.

    analyze_interview()   transcript + interview setup -> evaluation report
    normalise_report()    validates a report and recomputes every count and
                          score. Used on the model's output and again on the
                          interviewer's edited copy (interview_routes.py),
                          so scores are never taken from the model's or the
                          browser's arithmetic.

A short transcript is evaluated in one request. A long one (or one whose
single-request reply is cut off) is split into parts: each part's Q&A
pairs are evaluated separately, then one more request writes the summary
and skill assessment from the merged Q&A list.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict
from typing import Any

import httpx

BHARATAI_API_URL = os.getenv(
    "BHARATAI_API_URL",
    "http://115.112.206.245/api/chat/completions",
)
QWEN_MODEL = os.getenv("INTERVIEW_LLM_MODEL", "qwen3-27b")
BHARATAI_API_KEY = os.getenv("BHARATAI_API_KEY", "").strip()
REQUEST_TIMEOUT = float(os.getenv("INTERVIEW_LLM_TIMEOUT", "180"))
MAX_TOKENS = int(os.getenv("INTERVIEW_LLM_MAX_TOKENS", "12000"))
# Transcripts longer than this (characters) are evaluated in parts.
CHUNK_CHARS = int(os.getenv("INTERVIEW_CHUNK_CHARS", "36000"))

# Stored with each evaluation (interview_evaluations.model).
MODEL_KEY = "qwen"
MODEL_LABEL = "Qwen3 27B"

EVALUATIONS = ("Correct", "Partially Correct", "Incorrect", "Unable to Evaluate")
PROFICIENCY_LEVELS = (
    "Advanced", "Intermediate", "Beginner", "Not Demonstrated", "Insufficient Evidence",
)
# The interviewer's own call, entered by hand. The model never sets it.
INTERVIEWER_DECISIONS = ("", "Strongly recommend", "Recommend", "On hold", "Do not recommend")
UNCLASSIFIED = "Unclassified"
SCORING_RULE = (
    "Correct = 1, Partially Correct = 0.5, Incorrect = 0; "
    "Unable to Evaluate is left out of the denominator"
)

_PART_OVERLAP_CHARS = 1500
_PARALLEL_PARTS = 2


class InterviewAnalysisError(RuntimeError):
    """Raised when the LLM request or structured response fails."""


class _TruncatedReply(InterviewAnalysisError):
    """The model hit max_tokens before finishing its JSON."""


# ============================================================
# PROMPTS
# ============================================================

_EVALUATION_RULES = """
The transcript comes from automatic speech recognition WITHOUT speaker labels.
Work out from context who is speaking: the interviewer asks questions; the
candidate (participant) answers them. Recognition errors are possible — judge
the meaning of an answer, not its exact wording.

Pair each clearly identifiable interviewer question with the candidate's answer.
Preserve the meaning of the answer; do not silently improve it. Skip small talk,
greetings and logistics — only real interview questions count.

For every Q&A pair:
- map it to one of the supplied required skills when appropriate, using the
  skill name exactly as supplied; use "Unclassified" if none fits confidently;
- evaluate it as exactly one of: "Correct", "Partially Correct", "Incorrect",
  "Unable to Evaluate";
- give an accurate expected answer, or the correction for a partial/incorrect
  answer; for a correct answer give a concise reference answer;
- in remarks, explain the evaluation with specific evidence from the answer and
  name any missing points;
- never mark an answer incorrect only because its wording differs from the
  reference;
- use "Unable to Evaluate" when the question or answer is unclear, missing, or
  not something that can be judged reliably (e.g. opinions, personal history).

Do not invent questions, answers, candidate details or evidence. Do not make a
hiring decision. Keep feedback professional, fair and evidence-based.
"""

_PROFICIENCY_RULES = """
Assess each required skill using interview evidence only:
- Advanced: accurate, detailed answers across several relevant questions;
  explains trade-offs and applies concepts.
- Intermediate: sound core understanding with some gaps.
- Beginner: basic or inconsistent understanding.
- Not Demonstrated: no relevant evidence for this skill.
- Insufficient Evidence: too few or ambiguous answers to assign a reliable level.
"""

_QA_ITEM_SCHEMA = """{
      "question": "question as asked",
      "related_skill": "one supplied skill or Unclassified",
      "participant_answer": "answer as given",
      "evaluation": "Correct|Partially Correct|Incorrect|Unable to Evaluate",
      "correct_answer": "reference answer or correction",
      "remarks": "evidence and missing points"
    }"""

_SUMMARY_SCHEMA = """
  "interview_summary": "short evidence-based summary of the interview",
  "skill_assessment": [
    {
      "skill": "supplied skill name",
      "proficiency_level": "Advanced|Intermediate|Beginner|Not Demonstrated|Insufficient Evidence",
      "evidence": "brief explanation grounded in the assessed answers"
    }
  ],
  "strengths": ["..."],
  "improvement_areas": ["..."],
  "conclusion": "evidence-based conclusion; no hiring decision\""""

SYSTEM_PROMPT = (
    "You are Vidatha's interview evaluator. Analyse only the supplied transcript "
    "and the interviewer-provided required skills.\n"
    + _EVALUATION_RULES + _PROFICIENCY_RULES +
    "\nReturn ONLY valid JSON — no Markdown fences, no commentary — matching:\n"
    "{\n  \"qa_analysis\": [\n    " + _QA_ITEM_SCHEMA + "\n  ],"
    + _SUMMARY_SCHEMA + "\n}\n"
)

PART_SYSTEM_PROMPT = (
    "You are Vidatha's interview evaluator. You receive ONE PART of a long "
    "interview transcript (`transcript_part`), plus a little of the text before "
    "it (`previous_context`) and after it (`next_context`).\n"
    "Evaluate only questions that are asked inside `transcript_part`. Use "
    "`next_context` only to complete the answer to a question asked near the end "
    "of the part. Never evaluate a question that is asked inside "
    "`previous_context` or `next_context` — another part covers it.\n"
    + _EVALUATION_RULES +
    "\nReturn ONLY valid JSON — no Markdown fences, no commentary — matching:\n"
    "{\n  \"qa_analysis\": [\n    " + _QA_ITEM_SCHEMA + "\n  ]\n}\n"
    "Return {\"qa_analysis\": []} if the part contains no interview questions.\n"
)

SUMMARY_SYSTEM_PROMPT = (
    "You are Vidatha's interview evaluator. You receive the evaluated question-"
    "and-answer pairs of a whole interview (already judged) and the interviewer-"
    "provided required skills. Write the overall assessment from that evidence "
    "only. Do not re-judge the answers, do not invent evidence and do not make a "
    "hiring decision.\n"
    + _PROFICIENCY_RULES +
    "\nReturn ONLY valid JSON — no Markdown fences, no commentary — matching:\n{"
    + _SUMMARY_SCHEMA + "\n}\n"
)


# ============================================================
# MODEL OUTPUT -> JSON
# ============================================================

_THINK_BLOCK = re.compile(r"<think>.*?(</think>|$)", re.IGNORECASE | re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """
    The first complete JSON object in a model reply.

    Drops Qwen3 <think>…</think> reasoning (whose braces would otherwise be
    mistaken for the answer) and Markdown fences, then tolerates leading
    commentary and trailing text or a second JSON object (the usual cause of
    "Extra data" JSONDecodeErrors). Braces inside strings are handled by the
    JSON decoder itself.
    """
    if not isinstance(text, str) or not text.strip():
        raise InterviewAnalysisError("Qwen returned an empty response.")

    cleaned = _THINK_BLOCK.sub("", text).strip().lstrip("﻿")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    if not cleaned:
        raise InterviewAnalysisError("Qwen returned only reasoning, with no JSON answer.")

    decoder = json.JSONDecoder()
    last_error = None
    for start in (i for i, char in enumerate(cleaned) if char == "{"):
        try:
            result, _end = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(result, dict):
            return result

    if last_error:
        raise InterviewAnalysisError(f"Qwen returned invalid JSON: {last_error}") from last_error
    raise InterviewAnalysisError("Qwen did not return a JSON object.")


# ============================================================
# NORMALISING / SCORING
# ============================================================

_EVALUATION_ALIASES = {
    "correct": "Correct",
    "fully correct": "Correct",
    "partially correct": "Partially Correct",
    "partially_correct": "Partially Correct",
    "partial": "Partially Correct",
    "incorrect": "Incorrect",
    "wrong": "Incorrect",
    "unable to evaluate": "Unable to Evaluate",
    "unable_to_evaluate": "Unable to Evaluate",
    "not evaluated": "Unable to Evaluate",
}

_LEVEL_BY_FOLD = {level.casefold(): level for level in PROFICIENCY_LEVELS}


def _text(value: Any, limit: int = 5000) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).strip()[:limit]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("text") or item.get("description") or item.get("point") or ""
        text = _text(item, 1000)
        if text:
            items.append(text)
    return items[:30]


def clean_skills(skills: Any) -> list[str]:
    """Trimmed, de-duplicated (case-insensitively) skill names, in order."""
    seen = set()
    result = []
    for skill in skills if isinstance(skills, list) else []:
        name = _text(skill, 120)
        if name and name.casefold() not in seen and name.casefold() != UNCLASSIFIED.casefold():
            seen.add(name.casefold())
            result.append(name)
    return result[:40]


def _score(correct: int, partial: int, incorrect: int):
    evaluable = correct + partial + incorrect
    if not evaluable:
        return None
    return round((correct + 0.5 * partial) / evaluable * 100)


def normalise_report(
    data: dict[str, Any],
    required_skills: list[str],
    *,
    from_model: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    A clean evaluation report from `data` (the model's JSON, or the
    interviewer's edited report). Every count and score is recomputed here.

    from_model=True applies the evidence guardrails to proficiency levels
    (no questions -> Not Demonstrated; fewer than two judgeable answers ->
    Insufficient Evidence). For the interviewer's edits their chosen level
    is kept — it is their assessment.
    """
    if not isinstance(data, dict):
        raise InterviewAnalysisError("The evaluation must be a JSON object.")
    qa = data.get("qa_analysis")
    if not isinstance(qa, list):
        raise InterviewAnalysisError("The evaluation is missing its question-and-answer list.")

    skills = clean_skills(required_skills)
    skill_by_fold = {s.casefold(): s for s in skills}

    rows = []
    for item in qa:
        if not isinstance(item, dict):
            continue
        question = _text(item.get("question"))
        answer = _text(item.get("participant_answer"))
        if not question and not answer:
            continue
        raw_eval = _text(item.get("evaluation"), 60)
        evaluation = _EVALUATION_ALIASES.get(raw_eval.casefold(), raw_eval)
        if evaluation not in EVALUATIONS:
            evaluation = "Unable to Evaluate"
        skill = skill_by_fold.get(_text(item.get("related_skill"), 120).casefold(), UNCLASSIFIED)
        rows.append({
            "question_number": len(rows) + 1,
            "question": question,
            "related_skill": skill,
            "participant_answer": answer,
            "evaluation": evaluation,
            "correct_answer": _text(item.get("correct_answer")),
            "remarks": _text(item.get("remarks")),
        })

    def tally(items):
        return {
            "correct": sum(r["evaluation"] == "Correct" for r in items),
            "partially_correct": sum(r["evaluation"] == "Partially Correct" for r in items),
            "incorrect": sum(r["evaluation"] == "Incorrect" for r in items),
            "unable_to_evaluate": sum(r["evaluation"] == "Unable to Evaluate" for r in items),
        }

    supplied = {}
    for entry in data.get("skill_assessment") or []:
        if isinstance(entry, dict) and entry.get("skill"):
            supplied[_text(entry["skill"], 120).casefold()] = entry

    by_skill = defaultdict(list)
    for row in rows:
        by_skill[row["related_skill"]].append(row)

    skill_assessment = []
    for skill in skills:
        skill_rows = by_skill.get(skill, [])
        counts = tally(skill_rows)
        judged = counts["correct"] + counts["partially_correct"] + counts["incorrect"]
        entry = supplied.get(skill.casefold(), {})
        level = _LEVEL_BY_FOLD.get(_text(entry.get("proficiency_level"), 60).casefold())
        if from_model or not level:
            if not skill_rows:
                level = "Not Demonstrated"
            elif judged < 2:
                # Do not overstate proficiency from a single or unjudgeable answer.
                level = "Insufficient Evidence"
            elif not level:
                level = "Insufficient Evidence"
        skill_assessment.append({
            "skill": skill,
            "questions_assessed": len(skill_rows),
            **counts,
            "score_percent": _score(counts["correct"], counts["partially_correct"], counts["incorrect"]),
            "proficiency_level": level,
            "evidence": _text(entry.get("evidence")),
        })

    totals = tally(rows)
    decision = _text(data.get("interviewer_decision"), 60)
    if decision not in INTERVIEWER_DECISIONS or from_model:
        decision = ""

    source_details = details if details is not None else data.get("interview_details") or {}
    return {
        "interview_details": {
            "candidate_name": _text(source_details.get("candidate_name"), 200),
            "interviewer_name": _text(source_details.get("interviewer_name"), 200),
            "position": _text(source_details.get("position"), 200),
            "interview_type": _text(source_details.get("interview_type"), 60) or "Technical",
            "required_skills": skills,
        },
        "interview_summary": _text(data.get("interview_summary")),
        "qa_analysis": rows,
        "skill_assessment": skill_assessment,
        "unclassified_questions": len(by_skill.get(UNCLASSIFIED, [])),
        "strengths": _text_list(data.get("strengths")),
        "improvement_areas": _text_list(data.get("improvement_areas")),
        "conclusion": _text(data.get("conclusion")),
        "scoring": {
            "total_questions": len(rows),
            **totals,
            "score_percent": _score(totals["correct"], totals["partially_correct"], totals["incorrect"]),
            "scoring_rule": SCORING_RULE,
        },
        "interviewer_decision": decision,
        "interviewer_notes": "" if from_model else _text(data.get("interviewer_notes")),
    }


# ============================================================
# BHARATAI REQUESTS
# ============================================================

async def _chat(client: httpx.AsyncClient, messages: list[dict]) -> tuple[str, str]:
    """(content, finish_reason) for one chat completion."""
    body = {
        "model": QWEN_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {BHARATAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = await client.post(BHARATAI_API_URL, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise InterviewAnalysisError(
            f"BharatAI did not answer within {REQUEST_TIMEOUT:.0f} seconds."
        ) from exc
    except httpx.HTTPError as exc:
        raise InterviewAnalysisError(f"Could not reach BharatAI: {exc}") from exc

    if response.status_code >= 400:
        raise InterviewAnalysisError(
            f"BharatAI API returned HTTP {response.status_code}: {response.text[:1200]}"
        )
    try:
        choice = response.json()["choices"][0]
        content = choice["message"]["content"] or ""
        finish_reason = choice.get("finish_reason") or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise InterviewAnalysisError("Unexpected BharatAI response format.") from exc
    return content, finish_reason


async def _chat_json(client: httpx.AsyncClient, system: str, payload: dict) -> dict[str, Any]:
    """
    One JSON answer from the model. A reply cut off at max_tokens raises
    _TruncatedReply; an unparseable one is asked for again once.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    content, finish_reason = await _chat(client, messages)
    if finish_reason == "length":
        raise _TruncatedReply("The evaluation was cut off before it finished.")
    try:
        return _extract_json(content)
    except InterviewAnalysisError:
        messages += [
            {"role": "assistant", "content": content[:4000]},
            {"role": "user", "content": (
                "That reply was not one valid JSON object. Reply again with ONLY "
                "the JSON object described in the instructions — no reasoning, "
                "no Markdown, no commentary."
            )},
        ]
        content, finish_reason = await _chat(client, messages)
        if finish_reason == "length":
            raise _TruncatedReply("The evaluation was cut off before it finished.")
        return _extract_json(content)


def _split_transcript(text: str, size: int) -> list[str]:
    """Consecutive parts of at most ~`size` characters, cut between sentences."""
    pieces = [p for p in re.split(r"(?<=[.?!])\s+|\n+", text) if p.strip()]
    parts, current = [], ""
    for piece in pieces:
        while len(piece) > size:  # one enormous "sentence": hard-cut it
            if current:
                parts.append(current)
                current = ""
            parts.append(piece[:size])
            piece = piece[size:]
        if current and len(current) + 1 + len(piece) > size:
            parts.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        parts.append(current)
    return parts


async def _evaluate_in_parts(
    client: httpx.AsyncClient, transcript: str, setup: dict, part_chars: int
) -> dict[str, Any]:
    parts = _split_transcript(transcript, part_chars)
    limiter = asyncio.Semaphore(_PARALLEL_PARTS)

    async def evaluate_part(index: int) -> list:
        payload = {
            **setup,
            "part": f"{index + 1} of {len(parts)}",
            "previous_context": parts[index - 1][-_PART_OVERLAP_CHARS:] if index else "",
            "transcript_part": parts[index],
            "next_context": parts[index + 1][:_PART_OVERLAP_CHARS] if index + 1 < len(parts) else "",
        }
        async with limiter:
            try:
                result = await _chat_json(client, PART_SYSTEM_PROMPT, payload)
            except _TruncatedReply as exc:
                raise InterviewAnalysisError(
                    f"Part {index + 1} of the interview produced more output than the model "
                    "can return. Lower INTERVIEW_CHUNK_CHARS and try again."
                ) from exc
        qa = result.get("qa_analysis")
        return qa if isinstance(qa, list) else []

    part_results = await asyncio.gather(*(evaluate_part(i) for i in range(len(parts))))

    # Overlapping context can make two parts report the same question.
    merged, seen = [], set()
    for qa in part_results:
        for item in qa:
            if not isinstance(item, dict):
                continue
            key = re.sub(r"\W+", " ", str(item.get("question", ""))).strip().casefold()
            if key and key in seen:
                continue
            seen.add(key)
            merged.append(item)

    summary = await _chat_json(client, SUMMARY_SYSTEM_PROMPT, {
        **setup,
        "qa_analysis": [
            {
                "question_number": n,
                "question": _text(item.get("question"), 600),
                "related_skill": item.get("related_skill"),
                "participant_answer": _text(item.get("participant_answer"), 600),
                "evaluation": item.get("evaluation"),
                "remarks": _text(item.get("remarks"), 600),
            }
            for n, item in enumerate(merged, start=1)
        ],
    })
    return {**summary, "qa_analysis": merged}


async def analyze_interview(
    transcript: str,
    required_skills: list[str],
    position: str = "",
    candidate_name: str = "",
    interviewer_name: str = "",
    interview_type: str = "Technical",
) -> dict[str, Any]:
    """Evaluate a completed interview transcript; returns a normalised report."""
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Transcript is required.")
    skills = clean_skills(required_skills)
    if not skills:
        raise ValueError("At least one required skill must be provided by the interviewer.")
    if not BHARATAI_API_KEY:
        raise InterviewAnalysisError("BHARATAI_API_KEY is not configured in the backend environment.")

    details = {
        "candidate_name": (candidate_name or "").strip(),
        "interviewer_name": (interviewer_name or "").strip(),
        "position": (position or "").strip(),
        "interview_type": (interview_type or "").strip() or "Technical",
    }
    setup = {**details, "required_skills": skills}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if len(transcript) <= CHUNK_CHARS:
            try:
                data = await _chat_json(client, SYSTEM_PROMPT, {**setup, "transcript": transcript})
            except _TruncatedReply:
                # Too many Q&A pairs for one reply: evaluate it in halves.
                data = await _evaluate_in_parts(
                    client, transcript, setup, max(4000, len(transcript) // 2 + 1)
                )
        else:
            data = await _evaluate_in_parts(client, transcript, setup, CHUNK_CHARS)

    return normalise_report(data, skills, from_model=True, details=details)




