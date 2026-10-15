"""
MeetMind Interview template — HTTP routes (/api/interview/*).

Included by app.py. Everything here reads and writes the interview tables
(interview_database.py) only, never meetings or consultations. Recordings
made in the Interview template are saved as interviews by app.py's
_store_recording(); this router serves them back.

    GET  /api/interview/profile                    interviewer / organisation letterhead
    GET  /api/interview/profile/{logo|signature}
    POST /api/interview/profile
    POST /api/interview/analyze                    evaluate with Qwen, save as a draft
    GET  /api/interview/interviews                 history (admins: ?scope=all)
    GET  /api/interview/interviews/{id}
    GET  /api/interview/interviews/{id}/audio
    PATCH /api/interview/interviews/{id}           save the interview setup
    PUT  /api/interview/interviews/{id}/evaluation save the interviewer's edited report

Every route needs a signed-in user; an interview is visible to its owner
and to admins.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import audio_storage
import auth
import interview_database as idb
from interview_analysis import (
    MODEL_KEY,
    MODEL_LABEL,
    InterviewAnalysisError,
    analyze_interview,
    clean_skills,
    normalise_report,
)

logger = logging.getLogger("meetmind.interview")

interview_router = APIRouter(prefix="/api/interview", tags=["Interview Template"])


# ============================================================
# REQUEST MODELS
# ============================================================

class InterviewSetup(BaseModel):
    candidate_name: str = ""
    interviewer_name: str = ""
    position: str = ""
    interview_type: str = "Technical"
    required_skills: List[str] = Field(default_factory=list)


class InterviewAnalysisRequest(InterviewSetup):
    transcript: str = ""
    # The interview the evaluation is saved to. Without one, the interview
    # holding this transcript is reused or created.
    interview_id: Optional[int] = None


class EvaluationSaveRequest(BaseModel):
    # The report as the interviewer left it (see normalise_report()).
    evaluation: dict
    # True when saved because the interviewer downloaded it (status "final").
    final: bool = True


# ============================================================
# HELPERS
# ============================================================

def _clean_setup(setup: InterviewSetup) -> dict:
    interview_type = (setup.interview_type or "").strip()
    return {
        "candidate_name": setup.candidate_name.strip()[:200],
        "interviewer_name": setup.interviewer_name.strip()[:200],
        "position": setup.position.strip()[:200],
        "interview_type": interview_type if interview_type in idb.INTERVIEW_TYPES else "Technical",
        "required_skills": clean_skills(setup.required_skills),
    }


def _title_for(setup: dict) -> Optional[str]:
    """An interview is listed as "Candidate · Position" once either is known."""
    title = " · ".join(part for part in (setup.get("candidate_name"), setup.get("position")) if part)
    return title[:200] or None


def _require_interview_access(interview_id: int, user: dict) -> dict:
    interview = idb.get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found.")
    if interview["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You don't have access to that interview.")
    return interview


def _save_setup(interview_id: int, setup: dict) -> dict:
    fields = dict(setup)
    title = _title_for(setup)
    if title:
        fields["title"] = title
    return idb.update_interview(interview_id, **fields)


def _setup_payload(interview: dict) -> dict:
    return {
        "candidate_name": interview["candidate_name"],
        "interviewer_name": interview["interviewer_name"],
        "position": interview["position"],
        "interview_type": interview["interview_type"],
        "required_skills": interview["required_skills"],
    }


def _evaluation_payload(evaluation: Optional[dict]) -> Optional[dict]:
    if not evaluation:
        return None
    model = evaluation.get("model")
    return {
        **evaluation["report"],
        "status": evaluation["status"],
        "model": model,
        "modelLabel": MODEL_LABEL if model == MODEL_KEY else model,
        "createdAt": evaluation["created_at"],
        "updatedAt": evaluation["updated_at"],
        "finalizedAt": evaluation["finalized_at"],
    }


def _interview_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "candidateName": row["candidate_name"],
        "position": row["position"],
        "interviewType": row["interview_type"],
        "requiredSkills": row["required_skills"],
        "createdAt": row["created_at"],
        "durationSeconds": row["duration_seconds"],
        "transcriptChars": row["transcript_chars"] or 0,
        "hasAudio": row["audio_bytes"] is not None,
        "evaluationStatus": row["evaluation_status"],
        "scorePercent": row["score_percent"],
        "totalQuestions": row["total_questions"],
        "evaluationUpdatedAt": row["evaluation_updated_at"],
        "finalizedAt": row["finalized_at"],
        "userId": row["user_id"],
        "username": row["username"],
        "email": row["email"],
    }


def _interview_payload(interview: dict) -> dict:
    return {
        "id": interview["id"],
        "title": interview["title"],
        "createdAt": interview["created_at"],
        "durationSeconds": interview["duration_seconds"],
        "transcript": interview["transcript"],
        "setup": _setup_payload(interview),
        "evaluation": _evaluation_payload(idb.get_evaluation(interview["id"])),
        **audio_storage.audio_fields(
            "interview_audio",
            interview["id"],
            f"/api/interview/interviews/{interview['id']}/audio",
        ),
        # The letterhead belongs to whoever recorded the interview, so an
        # admin viewing it sees that interviewer's letterhead, not their own.
        "interviewerProfile": _profile_payload(idb.get_profile(interview["user_id"])),
        "userId": interview["user_id"],
        "username": interview["username"],
        "email": interview["email"],
    }


# ============================================================
# INTERVIEWER / ORGANISATION PROFILE
# ============================================================

PROFILE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
PROFILE_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


async def _read_profile_image(upload: Optional[UploadFile], field_name: str) -> Optional[tuple]:
    """Validate an optional uploaded profile image; (bytes, mime) or None."""
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in PROFILE_IMAGE_MIME:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a PNG, JPG, JPEG, or WEBP image.")
    data = await upload.read(PROFILE_IMAGE_MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"{field_name} is empty.")
    if len(data) > PROFILE_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"{field_name} must not exceed 5 MB.")
    return data, PROFILE_IMAGE_MIME[suffix]


def _profile_payload(profile: Optional[dict]) -> Optional[dict]:
    """The profile as the frontend uses it, with URLs for its images."""
    if not profile:
        return None
    payload = {name: profile[name] for name in idb.INTERVIEW_PROFILE_TEXT_FIELDS}
    version = re.sub(r"[^0-9]", "", profile["updated_at"])
    for kind in ("logo", "signature"):
        payload[f"{kind}_url"] = (
            f"/api/interview/profile/{kind}?user_id={profile['user_id']}&v={version}"
            if profile[f"has_{kind}"]
            else None
        )
    payload["updated_at"] = profile["updated_at"]
    return payload


def _profile_owner_id(user: dict, user_id: Optional[int]) -> int:
    """Whose profile a request means: your own, or (admins) anyone's."""
    if user_id is None or user_id == user["id"]:
        return user["id"]
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_id


@interview_router.get("/profile")
async def get_profile(request: Request, user_id: Optional[int] = None):
    """The signed-in user's interviewer profile (admins: any user's)."""
    user = auth.require_user(request)
    return {"success": True, "profile": _profile_payload(idb.get_profile(_profile_owner_id(user, user_id)))}


@interview_router.get("/profile/{kind}")
async def get_profile_image(kind: str, request: Request, user_id: Optional[int] = None):
    """The profile's logo or signature image."""
    if kind not in ("logo", "signature"):
        raise HTTPException(status_code=404, detail="Not found.")
    user = auth.require_user(request)
    image = idb.get_profile_image(_profile_owner_id(user, user_id), kind)
    if not image:
        raise HTTPException(status_code=404, detail=f"No {kind} is saved.")
    data, mime = image
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


@interview_router.post("/profile")
async def save_profile(
    request: Request,
    interviewer_name: str = Form(...),
    organization_name: str = Form(""),
    designation: str = Form(""),
    department: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    logo: Optional[UploadFile] = File(None),
    signature: Optional[UploadFile] = File(None),
    remove_logo: bool = Form(False),
    remove_signature: bool = Form(False),
):
    """Save the signed-in user's interviewer / organisation letterhead."""
    user = auth.require_user(request)
    interviewer_name = interviewer_name.strip()
    if not interviewer_name:
        raise HTTPException(status_code=400, detail="Interviewer name is required.")

    try:
        logo_image = await _read_profile_image(logo, "Logo")
        signature_image = await _read_profile_image(signature, "Signature")
    finally:
        if logo is not None:
            await logo.close()
        if signature is not None:
            await signature.close()

    profile = idb.save_profile(
        user["id"],
        {
            "interviewer_name": interviewer_name,
            "organization_name": organization_name,
            "designation": designation,
            "department": department,
            "address": address,
            "phone": phone,
            "email": email,
            "website": website,
        },
        logo=logo_image or (idb.REMOVE_IMAGE if remove_logo else None),
        signature=signature_image or (idb.REMOVE_IMAGE if remove_signature else None),
    )
    logger.info("Interviewer profile saved for user_id=%s", user["id"])
    return {"success": True, "message": "Interviewer profile saved.", "profile": _profile_payload(profile)}


# ============================================================
# EVALUATION
# ============================================================

@interview_router.post("/analyze")
async def analyze_interview_endpoint(payload: InterviewAnalysisRequest, request: Request):
    """
    Evaluate the interview with Qwen and save the result to the interview
    as a draft (keeping the untouched AI copy). The setup sent with it is
    saved to the interview too.
    """
    user = auth.require_user(request)
    setup = _clean_setup(payload)
    if not setup["required_skills"]:
        raise HTTPException(status_code=400, detail="Enter at least one required skill.")

    if payload.interview_id:
        interview = _require_interview_access(payload.interview_id, user)
    else:
        transcript = (payload.transcript or "").strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="Record or upload the interview first.")
        interview = idb.get_interview(idb.find_or_create_interview(user["id"], transcript))

    # The saved transcript is the one evaluated, so the report always matches
    # the interview it is stored with.
    transcript = (interview["transcript"] or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="This interview has no transcript to evaluate.")

    interview = _save_setup(interview["id"], setup)

    try:
        report = await analyze_interview(
            transcript=transcript,
            required_skills=setup["required_skills"],
            position=setup["position"],
            candidate_name=setup["candidate_name"],
            interviewer_name=setup["interviewer_name"],
            interview_type=setup["interview_type"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InterviewAnalysisError as exc:
        logger.warning("Interview evaluation failed | interview_id=%s | %s", interview["id"], exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    saved = idb.save_evaluation(interview["id"], report, status="draft", model=MODEL_KEY, ai_draft=report)
    logger.info(
        "Interview evaluated | interview_id=%s | questions=%s | score=%s | user_id=%s",
        interview["id"],
        report["scoring"]["total_questions"],
        report["scoring"]["score_percent"],
        user["id"],
    )
    return {
        "success": True,
        "interview_id": interview["id"],
        "status": "draft",
        "review_required": True,
        "evaluation": _evaluation_payload(saved),
    }


# ============================================================
# SAVED INTERVIEWS (history of the Interview template)
# ============================================================

@interview_router.get("/interviews")
async def list_interviews(request: Request, scope: str = "mine"):
    """The user's interviews, newest first (admins: scope=all for everyone's)."""
    user = auth.require_user(request)
    if scope == "all":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        rows = idb.list_interviews()
    else:
        rows = idb.list_interviews(user_id=user["id"])
    return [_interview_row(row) for row in rows]


@interview_router.get("/interviews/{interview_id}")
async def get_interview(interview_id: int, request: Request):
    user = auth.require_user(request)
    return _interview_payload(_require_interview_access(interview_id, user))


@interview_router.get("/interviews/{interview_id}/audio")
async def get_interview_audio(interview_id: int, request: Request):
    user = auth.require_user(request)
    _require_interview_access(interview_id, user)
    return audio_storage.audio_response(
        request, "interview_audio", interview_id, f"interview_{interview_id}"
    )


@interview_router.patch("/interviews/{interview_id}")
async def update_interview_setup(interview_id: int, setup: InterviewSetup, request: Request):
    """Save the interview setup (candidate, interviewer, position, type, skills)."""
    user = auth.require_user(request)
    _require_interview_access(interview_id, user)
    interview = _save_setup(interview_id, _clean_setup(setup))
    return {"success": True, "title": interview["title"], "setup": _setup_payload(interview)}


@interview_router.put("/interviews/{interview_id}/evaluation")
async def save_interview_evaluation(interview_id: int, payload: EvaluationSaveRequest, request: Request):
    """
    Save the evaluation as the interviewer edited it. The frontend calls this
    when the report is downloaded, which marks it "final". Counts and scores
    are recomputed from the Q&A verdicts; the skills are the ones the report
    was evaluated against.
    """
    user = auth.require_user(request)
    _require_interview_access(interview_id, user)
    existing = idb.get_evaluation(interview_id)
    if not existing:
        raise HTTPException(status_code=400, detail="Evaluate this interview before saving its report.")

    incoming = payload.evaluation
    skills = (existing["report"].get("interview_details") or {}).get("required_skills") or []
    details = incoming.get("interview_details") if isinstance(incoming.get("interview_details"), dict) else {}
    try:
        report = normalise_report(incoming, skills, from_model=False, details=details)
    except InterviewAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = idb.save_evaluation(interview_id, report, status="final" if payload.final else "draft")
    logger.info(
        "Interview evaluation saved | interview_id=%s | status=%s | user_id=%s",
        interview_id,
        saved["status"],
        user["id"],
    )
    return {"success": True, "evaluation": _evaluation_payload(saved)}
