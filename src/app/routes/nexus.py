from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import time
import uuid

from src.app import dependencies, models

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

class MapPinCreate(BaseModel):
    name: str
    lat: float
    lng: float
    google_place_id: Optional[str] = None
    notes: Optional[str] = None

# --- CODING CANVAS ROUTES ---

@router.post("/projects", summary="Create a new Coding Workspace")
async def create_project(
    payload: ProjectCreate,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    project = models.Project(name=payload.name, description=payload.description, user_id=user.id)
    db.add(project)
    db.flush() # Generate ID

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
    try:
        p_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(400, "Invalid Project ID")

    project = db.get(models.Project, p_uuid)
    if not project or project.user_id != user.id:
        raise HTTPException(404, "Project not found")

    # MOCK BUILD LOGS (Simulating Docker Container Output)
    logs = [
        "Initializing Vylarc Core Build Environment...",
        "Allocating Sandbox (2 CPU, 1GB RAM)...",
        "Mounting File System...",
    ]
    for file in project.files:
        logs.append(f"> Compiling {file.filename}...")
        # In a real app, we would actually run code here via subprocess or Docker
    
    logs.append("Running Tests... [PASS]")
    logs.append("Build Successful. Artifact generated.")
    
    project.status = "completed"
    db.commit()

    return {
        "status": "success",
        "logs": logs,
        "artifact_url": "https://vylarc.com/api/download/mock_artifact.zip" 
    }

# --- SMART MAPPING ROUTES ---

@router.get("/map/pins", summary="Get Saved Pins")
async def get_map_pins(
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Returns all map pins saved by the user.
    """
    pins = db.query(models.MapPin).filter(models.MapPin.user_id == user.id).all()
    return {"pins": pins}

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
    return {"message": "Location pinned to Cyber Grid.", "id": str(new_pin.id)}

# --- DRIVE / FILES ROUTES ---

@router.get("/files", summary="List Uploaded Files")
async def list_files(
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Lists files for the Drive module.
    """
    files = db.query(models.FileUpload).filter(models.FileUpload.user_id == user.id).order_by(models.FileUpload.timestamp.desc()).all()
    
    # Format for frontend
    file_list = []
    for f in files:
        # Determine simple type for UI icon
        ftype = "doc"
        if f.filename.endswith(('.png', '.jpg', '.jpeg')): ftype = "image"
        elif f.filename.endswith(('.xls', '.xlsx', '.csv')): ftype = "sheet"
        elif f.filename.endswith('.zip'): ftype = "zip"
        
        file_list.append({
            "id": str(f.id),
            "name": f.filename,
            "type": ftype,
            "size": f"{f.filesize / 1024:.1f} KB" if f.filesize else "Unknown",
            "date": f.timestamp.strftime("%Y-%m-%d"),
            "url": f.drive_url or "#"
        })
        
    return {"files": file_list}