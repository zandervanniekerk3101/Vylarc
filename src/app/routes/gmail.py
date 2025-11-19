import base64
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.app import dependencies, models
from src.app.services import google_service

router = APIRouter()

class EmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str

@router.get("/list", summary="List Emails")
async def list_emails(
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    service = google_service.get_gmail_service(user.id, db)
    if not service:
        raise HTTPException(401, "Google Account not connected. Please sign in with Google.")

    try:
        # Get list of message IDs
        results = service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])
        
        email_list = []
        for msg in messages:
            # Fetch details for each
            details = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = details['payload']['headers']
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            
            email_list.append({
                "id": msg['id'],
                "from": sender,
                "subject": subject,
                "preview": details.get('snippet', ''),
                "date": "Today", # Simplified
                "unread": 'UNREAD' in details.get('labelIds', [])
            })
            
        return {"messages": email_list}
    except Exception as e:
        raise HTTPException(500, f"Gmail Error: {str(e)}")

@router.post("/send", summary="Send Email")
async def send_email(
    payload: EmailSendRequest,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    service = google_service.get_gmail_service(user.id, db)
    if not service:
        raise HTTPException(401, "Google Account not connected.")

    try:
        message = MIMEText(payload.body)
        message['to'] = payload.to
        message['subject'] = payload.subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(500, f"Failed to send: {str(e)}")