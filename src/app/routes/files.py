import base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from src.app import dependencies, models
from src.app.services import google_service

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

@router.post("/upload", summary="Upload to Drive")
async def upload_file(
    payload: FileUploadRequest,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    service = google_service.get_drive_service(user.id, db)
    
    # 1. Upload to Google Drive (if connected)
    drive_link = None
    file_size = 0
    
    try:
        # Decode Base64
        file_data = base64.b64decode(payload.file_base64)
        file_size = len(file_data)
        
        if service:
            from googleapiclient.http import MediaIoBaseUpload
            import io
            
            file_metadata = {'name': payload.filename}
            media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype='application/octet-stream', resumable=True)
            
            gfile = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            drive_link = gfile.get('webViewLink')
    except Exception as e:
        # Log but continue to save to DB so user sees something
        print(f"Drive Upload Error: {e}")

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