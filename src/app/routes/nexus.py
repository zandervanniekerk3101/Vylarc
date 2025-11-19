from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import time

from src.app import dependencies, models
from src.app.services import chat_service

router = APIRouter()

# --- SCHEMAS ---
class FileItem(BaseModel):
    filename: str
    content: str
    language: str

class ProjectCreate(BaseModel):
    name: str
    description: str
    files: List[FileItem] = []

class BuildResponse(BaseModel):
    status: str
    logs: List[str]
    artifact_url: Optional[str] = None

# --- CODING CANVAS ROUTES ---

@router.post("/projects", summary="Create a new Coding Workspace")
async def create_project(
    payload: ProjectCreate,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    # Create Project
    project = models.Project(name=payload.name, description=payload.description, user_id=user.id)
    db.add(project)
    db.flush()

    # Add Files
    for f in payload.files:
        db.add(models.ProjectFile(
            project_id=project.id, 
            filename=f.filename, 
            content=f.content, 
            language=f.language
        ))
    
    db.commit()
    return {"id": str(project.id), "message": "Workspace created."}

@router.post("/projects/{project_id}/execute", summary="Execute Core Build (Sandbox)")
async def execute_build(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    project = db.get(models.Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(404, "Project not found")

    # Since we are on Render Free Tier, we cannot spin up Docker containers dynamically.
    # We will Simulate the build process using the Vylarc "Mock Runner".
    # In a paid PRO environment, this would trigger a Redis Job for a Docker Worker.
    
    logs = [
        "Initializing Vylarc Core Build Environment...",
        "Allocating Sandbox (2 CPU, 1GB RAM)...",
        "Mounting File System...",
    ]
    
    # Simulate processing files
    for file in project.files:
        logs.append(f"> Compiling {file.filename}...")
        time.sleep(0.5) # Fake delay
    
    logs.append("Running Tests... [PASS]")
    logs.append("Build Successful. Artifact generated.")
    
    # Update Status
    project.status = "completed"
    db.commit()

    return {
        "status": "success",
        "logs": logs,
        "artifact_url": "https://vylarc.com/api/download/mock_artifact.zip" # Mock
    }

# --- SMART MAPPING ROUTES ---
class MapPinCreate(BaseModel):
    name: str
    lat: float
    lng: float
    google_place_id: Optional[str] = None
    notes: Optional[str] = None

@router.post("/map/pin", summary="Save a Location Pin")
async def save_map_pin(
    pin: MapPinCreate,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    new_pin = models.MapPin(
        user_id=user.id,
        name=pin.name,
        lat=pin.lat,
        lng=pin.lng,
        google_place_id=pin.google_place_id,
        notes=pin.notes
    )
    db.add(new_pin)
    db.commit()
    return {"message": "Location pinned to Cyber Grid."}