"""
Copy the endpoint below into app.py, or include this router from app.py.
This route is separate from the existing MOM summary and mind-map routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List

from interview_analysis import analyze_interview, InterviewAnalysisError

interview_router = APIRouter(prefix="/api/interview", tags=["Interview Template"])


class InterviewAnalysisRequest(BaseModel):
    transcript: str = Field(min_length=1)
    required_skills: List[str] = Field(min_length=1)
    position: str = ""
    candidate_name: str = ""
    interviewer_name: str = ""
    interview_type: str = "Technical"


@interview_router.post("/analyze")
async def analyze_interview_endpoint(payload: InterviewAnalysisRequest):
    try:
        return await analyze_interview(
            transcript=payload.transcript,
            required_skills=payload.required_skills,
            position=payload.position,
            candidate_name=payload.candidate_name,
            interviewer_name=payload.interviewer_name,
            interview_type=payload.interview_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InterviewAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# In app.py add:
# from interview_routes import interview_router
# app.include_router(interview_router)
