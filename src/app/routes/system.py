from fastapi import APIRouter
from src.app.schemas.core import MessageResponse

router = APIRouter()

@router.get("/status", response_model=MessageResponse)
async def get_system_status():
    """
    Health check endpoint for Render.
    """
    return {"message": "System OK"}

@router.get("/version", response_model=MessageResponse)
async def get_system_version():
    """
    Returns the current API version.
    """
    return {"message": "Vylarc API Version 1.0.0"}