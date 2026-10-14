"""

MeetMind Interview Template analysis using BharatAI Qwen3-27B.

This module is additive: it does not modify the MOM summary or mind-map pipeline.

"""

from __future__ import annotations

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

class InterviewAnalysisError(RuntimeError):

    """Raised when the LLM request or structured response fails."""

SYSTEM_PROMPT = """

You are MeetMind's technical interview evaluator. Analyze only the supplied transcript

and interviewer-provided required skills. Do not invent questions, answers, candidate

details, or evidence.

The transcript may contain interviewer and participant turns. Pair each clearly

identifiable interviewer question with the relevant participant answer. Preserve the

meaning of the participant's answer; do not silently improve it.

For every Q&A pair:

- map it to one of the interviewer-provided required skills when appropriate;

- use "Unclassified" if no skill maps confidently;

- evaluate as exactly one of: "Correct", "Partially Correct", "Incorrect",

  "Unable to Evaluate";

- provide an accurate expected answer or correction for partial/incorrect answers;

- if the answer is already correct, provide a concise reference answer;

- explain the evaluation using specific evidence from the answer;

- never mark an answer incorrect merely because its wording differs from the reference;

- use "Unable to Evaluate" if the question/answer is unclear, missing, or not technical

  enough to judge reliably.

Assess skill levels using interview evidence only:

- Advanced: accurate, detailed answers across multiple relevant questions, explains

  trade-offs and applies concepts.

- Intermediate: sound core understanding with some gaps.

- Beginner: basic or inconsistent understanding.

- Not Demonstrated: no relevant evidence for this skill.

- Insufficient Evidence: too few or ambiguous answers to assign a reliable level.

Do not infer a hiring decision. Keep feedback professional, fair, and evidence-based.

Return ONLY valid JSON, with no Markdown fences or commentary, matching this schema:

{

  "interview_summary": "short evidence-based summary",

  "qa_analysis": [

    {

      "question_number": 1,

      "question": "question as asked",

      "related_skill": "one supplied skill or Unclassified",

      "participant_answer": "answer as given",

      "evaluation": "Correct|Partially Correct|Incorrect|Unable to Evaluate",

      "correct_answer": "reference answer or correction",

      "remarks": "evidence and missing points"

    }

  ],

  "skill_assessment": [

    {

      "skill": "skill name",

      "questions_assessed": 0,

      "correct": 0,

      "partially_correct": 0,

      "incorrect": 0,

      "unable_to_evaluate": 0,

      "proficiency_level": "Advanced|Intermediate|Beginner|Not Demonstrated|Insufficient Evidence",

      "evidence": "brief explanation grounded in assessed answers"

    }

  ],

  "strengths": ["..."],

  "improvement_areas": ["..."],

  "conclusion": "evidence-based conclusion; do not make a hiring decision",

  "scoring": {

    "total_questions": 0,

    "correct": 0,

    "partially_correct": 0,

    "incorrect": 0,

    "unable_to_evaluate": 0,

    "score_percent": 0,

    "scoring_rule": "Correct=1, Partially Correct=0.5, Incorrect=0; Unable to Evaluate excluded from denominator"

  }

}

"""

def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object from model output.

    Handles Markdown fences, leading commentary, and trailing text or a second
    JSON object (a common cause of ``Extra data`` JSONDecodeError failures).
    Braces inside quoted strings are ignored.
    """
    if not isinstance(text, str) or not text.strip():
        raise InterviewAnalysisError("Qwen returned an empty response.")

    cleaned = text.strip().lstrip("\ufeff")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    decoder = json.JSONDecoder()
    # Try each opening brace; raw_decode stops at the end of the first JSON value,
    # instead of failing because extra characters follow it.
    last_error = None
    for start in (i for i, char in enumerate(cleaned) if char == "{"):
        try:
            result, _end = decoder.raw_decode(cleaned[start:])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

    if last_error:
        raise InterviewAnalysisError(f"Qwen returned invalid JSON: {last_error}") from last_error
    raise InterviewAnalysisError("Qwen did not return a valid JSON object.")


def _normalise_and_score(data: dict[str, Any], required_skills: list[str]) -> dict[str, Any]:

    qa = data.get("qa_analysis")

    if not isinstance(qa, list):

        raise InterviewAnalysisError("Qwen response is missing the qa_analysis list.")

    allowed = {"Correct", "Partially Correct", "Incorrect", "Unable to Evaluate"}

    normalised_qa = []

    counts = {key: 0 for key in allowed}

    skill_names = [s.strip() for s in required_skills if s.strip()]

    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, item in enumerate(qa, start=1):

        if not isinstance(item, dict):

            continue

        evaluation = str(item.get("evaluation", "Unable to Evaluate")).strip()

        # Normalise common model variations without accepting arbitrary labels.

        aliases = {

            "partially correct": "Partially Correct",

            "partially_correct": "Partially Correct",

            "correct": "Correct",

            "incorrect": "Incorrect",

            "unable to evaluate": "Unable to Evaluate",

        }

        evaluation = aliases.get(evaluation.lower(), evaluation)

        if evaluation not in allowed:

            evaluation = "Unable to Evaluate"

        skill = str(item.get("related_skill", "Unclassified")).strip() or "Unclassified"

        # Match supplied skills case-insensitively; otherwise retain Unclassified.

        if skill_names:

            match = next((s for s in skill_names if s.casefold() == skill.casefold()), None)

            skill = match or ("Unclassified" if skill.casefold() == "unclassified" else skill)

            if skill not in skill_names and skill != "Unclassified":

                skill = "Unclassified"

        row = {

            "question_number": index,

            "question": str(item.get("question", "")).strip(),

            "related_skill": skill,

            "participant_answer": str(item.get("participant_answer", "")).strip(),

            "evaluation": evaluation,

            "correct_answer": str(item.get("correct_answer", "")).strip(),

            "remarks": str(item.get("remarks", "")).strip(),

        }

        normalised_qa.append(row)

        counts[evaluation] += 1

        if skill != "Unclassified":

            by_skill[skill].append(row)

    # Recompute counts and score server-side instead of trusting model arithmetic.

    evaluable = counts["Correct"] + counts["Partially Correct"] + counts["Incorrect"]

    earned = counts["Correct"] + (0.5 * counts["Partially Correct"])

    score = round((earned / evaluable) * 100) if evaluable else 0

    supplied_skill_assessment = data.get("skill_assessment", [])

    model_skill_by_name = {}

    if isinstance(supplied_skill_assessment, list):

        for entry in supplied_skill_assessment:

            if isinstance(entry, dict) and entry.get("skill"):

                model_skill_by_name[str(entry["skill"]).casefold()] = entry

    skill_assessment = []

    for skill in skill_names:

        rows = by_skill.get(skill, [])

        c = sum(r["evaluation"] == "Correct" for r in rows)

        p = sum(r["evaluation"] == "Partially Correct" for r in rows)

        i = sum(r["evaluation"] == "Incorrect" for r in rows)

        u = sum(r["evaluation"] == "Unable to Evaluate" for r in rows)

        model_entry = model_skill_by_name.get(skill.casefold(), {})

        level = str(model_entry.get("proficiency_level", "Insufficient Evidence"))

        valid_levels = {"Advanced", "Intermediate", "Beginner", "Not Demonstrated", "Insufficient Evidence"}

        if level not in valid_levels:

            level = "Insufficient Evidence"

        if not rows:

            level = "Not Demonstrated"

        elif len([r for r in rows if r["evaluation"] != "Unable to Evaluate"]) < 2:

            # Do not overstate proficiency from a single or unjudgeable answer.

            level = "Insufficient Evidence"

        skill_assessment.append({

            "skill": skill,

            "questions_assessed": len(rows),

            "correct": c,

            "partially_correct": p,

            "incorrect": i,

            "unable_to_evaluate": u,

            "proficiency_level": level,

            "evidence": str(model_entry.get("evidence", "")).strip(),

        })

    # Include Unclassified in Q&A but not as a requested skill proficiency.

    data["qa_analysis"] = normalised_qa

    data["skill_assessment"] = skill_assessment

    data["strengths"] = data.get("strengths") if isinstance(data.get("strengths"), list) else []

    data["improvement_areas"] = data.get("improvement_areas") if isinstance(data.get("improvement_areas"), list) else []

    data["interview_summary"] = str(data.get("interview_summary", "")).strip()

    data["conclusion"] = str(data.get("conclusion", "")).strip()

    data["scoring"] = {

        "total_questions": len(normalised_qa),

        "correct": counts["Correct"],

        "partially_correct": counts["Partially Correct"],

        "incorrect": counts["Incorrect"],

        "unable_to_evaluate": counts["Unable to Evaluate"],

        "score_percent": score,

        "scoring_rule": "Correct=1, Partially Correct=0.5, Incorrect=0; Unable to Evaluate excluded from denominator",

    }

    return data

async def analyze_interview(

    transcript: str,

    required_skills: list[str],

    position: str = "",

    candidate_name: str = "",

    interviewer_name: str = "",

    interview_type: str = "Technical",

) -> dict[str, Any]:

    """Analyze a completed transcript using the BharatAI Qwen3-27B gateway."""

    if not transcript or not transcript.strip():

        raise ValueError("Transcript is required.")

    skills = [s.strip() for s in required_skills if s and s.strip()]

    if not skills:

        raise ValueError("At least one required skill must be provided by the interviewer.")

    if not BHARATAI_API_KEY:

        raise InterviewAnalysisError("BHARATAI_API_KEY is not configured in the backend environment.")

    user_payload = {

        "position": position.strip(),

        "candidate_name": candidate_name.strip(),

        "interviewer_name": interviewer_name.strip(),

        "interview_type": interview_type.strip(),

        "required_skills": skills,

        "transcript": transcript.strip(),

    }

    headers = {

        "Authorization": f"Bearer {BHARATAI_API_KEY}",

        "Content-Type": "application/json",

    }

    body = {

        "model": QWEN_MODEL,

        "messages": [

            {"role": "system", "content": SYSTEM_PROMPT},

            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},

        ],

        "temperature": 0.1,

        "max_tokens": 12000,

    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:

        response = await client.post(BHARATAI_API_URL, headers=headers, json=body)

    if response.status_code >= 400:

        safe_body = response.text[:1200]

        raise InterviewAnalysisError(f"BharatAI API returned HTTP {response.status_code}: {safe_body}")

    try:

        api_data = response.json()

        content = api_data["choices"][0]["message"]["content"]

    except (ValueError, KeyError, IndexError, TypeError) as exc:

        raise InterviewAnalysisError("Unexpected BharatAI response format.") from exc

    parsed = _extract_json(content)

    parsed["interview_details"] = {

        "position": position.strip(),

        "candidate_name": candidate_name.strip(),

        "interviewer_name": interviewer_name.strip(),

        "interview_type": interview_type.strip(),

        "required_skills": skills,

    }

    return _normalise_and_score(parsed, skills)
