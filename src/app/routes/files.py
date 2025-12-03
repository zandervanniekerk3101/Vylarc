import base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from src.app import dependencies, models

router = APIRouter()


class FileUploadRequest(BaseModel):
    filename: str
    file_base64: str

@router.get("/list", summary="List Files")
async def list_files(
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    # Return local DB records (faster than querying Drive API every time)
    files = db.query(models.FileUpload).filter(models.FileUpload.user_id == user.id).order_by(models.FileUpload.timestamp.desc()).all()
    
    output = []
    for f in files:
        # Determine UI Icon type
        ftype = 'doc'
        if f.filename.endswith(('.jpg','.png')): ftype = 'image'
        elif f.filename.endswith(('.xls','.xlsx','.csv')): ftype = 'sheet'
        
        output.append({
            "id": str(f.id),
            "name": f.filename,
            "type": ftype,
            "size": f"{f.filesize / 1024:.1f} KB",
            "date": f.timestamp.strftime("%Y-%m-%d"),
            "url": f.drive_url or "#"
        })
    return {"files": output}

@router.post("/upload", summary="Upload file (local metadata only)")
async def upload_file(
    payload: FileUploadRequest,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    # Google Drive upload is disabled; we just store metadata.
    drive_link = None
    file_size = 0
    
    try:
        # Decode Base64
        file_data = base64.b64decode(payload.file_base64)
        file_size = len(file_data)
        
    except Exception as e:
        # Log but continue to save to DB so user sees something
        print(f"File decode error: {e}")

    # 2. Save Metadata to Vylarc DB
    db_file = models.FileUpload(
        user_id=user.id,
        filename=payload.filename,
        filesize=file_size,
        drive_url=drive_link,
        timestamp=datetime.now()
    )
    db.add(db_file)
    db.commit()
    
    return {"status": "success", "drive_url": drive_link}