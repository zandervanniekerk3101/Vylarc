from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from src.app import dependencies, models
from src.app.services import canvas_service

router = APIRouter()

class CanvasRequest(BaseModel):
    prompt: str

class CanvasResponse(BaseModel):
    research_summary: str
    files: Dict[str, str]

@router.post(
    "/generate",
    response_model=CanvasResponse,
    summary="Generate a coding project from a prompt using the Vylarc Coding Canvas"
)
async def generate_project(
    payload: CanvasRequest,
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """
    Triggers the Coding Canvas flow:
    1. Deep Search & Research
    2. Project Planning & File Generation
    3. Code Analysis & Self-Correction
    """
    try:
        result = canvas_service.run_coding_canvas_flow(payload.prompt)
        return CanvasResponse(
            research_summary=result["research_summary"],
            files=result["files"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canvas generation failed: {e}")
