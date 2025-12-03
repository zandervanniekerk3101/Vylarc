from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import uuid
import logging

from src.app import dependencies, models
from src.app.config import get_settings
from src.app.services import credit_service
from sqlalchemy import select

router = APIRouter()
settings = get_settings()

# --- SKU CONFIGURATION ---
# Mapped according to your Vylarc Project Brief
# These keys must match the 'SKU' or 'Product Name' in WooCommerce
SKU_TO_CREDITS = {
    # Pay-As-You-Go
    "vylarc_pack_2000": 2000,
    "vylarc_pack_10000": 10000,
    "vylarc_pack_30000": 30000,
    
    # Subscriptions
    "vylarc_sub_pro": 10000,      # Pro Tier
    "vylarc_sub_business": 80000, # Business Tier
    "vylarc_sub_enterprise": 400000 # Enterprise Tier
}

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

# --- WEBHOOKS ---

@router.post("/webhook/woocommerce", summary="WooCommerce Webhook Listener")
async def woocommerce_webhook(
    payload: Dict[Any, Any],
    x_wordpress_secret: str = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    """
    Receives order events from WooCommerce and grants credits.
    """
    if x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        raise HTTPException(403, "Invalid Secret")
    
    event = payload.get('event')
    logging.info(f"Received WooCommerce Webhook: {event}")

    if event == 'new_order':
        email = payload.get('customer_email')
        order_id = str(payload.get('order_id'))
        total_paid = float(payload.get('total', 0))
        items = payload.get('items', [])

        # 1. Find User
        user = db.scalar(select(models.User).where(models.User.email == email.lower()))
        if not user:
            logging.warning(f"WooCommerce Order {order_id}: User {email} not found. Skipping credit grant.")
            return {"status": "skipped", "reason": "user_not_found"}

        credits_granted = 0
        
        # 2. Process Items
        for item in items:
            # We check both SKU (if passed) or Name to match our config
            # The linker sends 'name', we might need to adjust linker to send SKU if possible
            # For now, we assume the product name might contain the key or we match loosely
            # Ideally, update the linker to send SKU.
            
            # Let's assume the 'name' in WooCommerce matches our keys or we add a mapping here.
            # For robustness, let's try to match the keys in the item name
            
            item_name = item.get('name', '').lower()
            quantity = int(item.get('quantity', 1))
            
            matched_sku = None
            for key in SKU_TO_CREDITS:
                if key in item_name: # Simple substring match
                    matched_sku = key
                    break
            
            if matched_sku:
                amount = SKU_TO_CREDITS[matched_sku] * quantity
                credits_granted += amount
                logging.info(f"Matched item '{item_name}' to {matched_sku}. Granting {amount} credits.")

        # 3. Grant Credits
        if credits_granted > 0:
            try:
                credit_service.grant_credits_to_user(
                    db=db,
                    user_id=user.id,
                    credits_to_add=credits_granted,
                    amount_paid=total_paid,
                    payment_method="WooCommerce",
                    transaction_id=f"wc_{order_id}"
                )
                db.commit()
                logging.info(f"Successfully granted {credits_granted} credits to {email} for Order {order_id}")
            except Exception as e:
                db.rollback()
                logging.error(f"Failed to grant credits for Order {order_id}: {e}")
                raise HTTPException(500, "Failed to process credits")
        else:
            logging.info(f"Order {order_id} contained no credit packages.")

    return {"status": "processed"}