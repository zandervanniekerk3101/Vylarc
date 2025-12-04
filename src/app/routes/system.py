from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from src.app import dependencies, models
from src.app.config import get_settings

router = APIRouter()
settings = get_settings()

# --- SCHEMAS ---
class SystemPromptUpdate(BaseModel):
    prompt: str

class UserStat(BaseModel):
    id: str
    name: str
    email: str
    last_active: str | None

# --- ROUTES ---

@router.get("/status")
async def get_system_status():
    """
    Health check endpoint for Render.
    """
    return {"message": "System OK"}

@router.get("/version")
async def get_system_version():
    """
    Returns the current API version.
    """
    return {"message": "Vylarc API Version 1.0.0"}

@router.get("/features", summary="Get Feature Flags")
async def get_feature_flags():
    """Returns server-side feature flags for client UI gating."""
    return {
        "enableTelephony": settings.ENABLE_TELEPHONY,
        "enableVoice": settings.ENABLE_VOICE,
        "enableGoogle": settings.ENABLE_GOOGLE_INTEGRATIONS,
    }

# --- ADMIN DASHBOARD ENDPOINTS ---

@router.get("/prompt", summary="Get System Prompt")
async def get_system_prompt(
    x_wordpress_secret: str = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    if x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        raise HTTPException(403, "Invalid Secret")
        
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "system_prompt").first()
    if not setting:
        return {"prompt": ""}
    return {"prompt": setting.value}

@router.post("/prompt", summary="Update System Prompt")
async def update_system_prompt(
    payload: SystemPromptUpdate,
    x_wordpress_secret: str = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    if x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        raise HTTPException(403, "Invalid Secret")
        
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "system_prompt").first()
    if not setting:
        setting = models.SystemSetting(key="system_prompt", value=payload.prompt)
        db.add(setting)
    else:
        setting.value = payload.prompt
    
    db.commit()
    return {"message": "System prompt updated."}

@router.get("/users", summary="Get Active Chat Users")
async def get_active_users(
    x_wordpress_secret: str = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    if x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        raise HTTPException(403, "Invalid Secret")
    
    # Find users who have at least one chat history entry
    # We join User and ChatHistory to filter
    users = (
        db.query(models.User)
        .join(models.ChatHistory, models.User.id == models.ChatHistory.user_id)
        .distinct()
        .all()
    )
    
    result = []
    for u in users:
        result.append({
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "last_active": str(u.updated_at)
        })
        
    return {"users": result}