import logging
from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.app.models import models
from src.app.utils import security
from src.app.config import get_settings

settings = get_settings()

def get_user_google_creds(user_id: str, db: Session) -> Credentials | None:
    """Retrieves and refreshes Google Credentials for a user."""
    db_creds = db.query(models.GoogleCredential).filter(models.GoogleCredential.user_id == user_id).first()
    
    if not db_creds or not db_creds.refresh_token:
        return None

    # Decrypt
    token = security.decrypt_data(db_creds.access_token)
    refresh = security.decrypt_data(db_creds.refresh_token)

    creds = Credentials(
        token=token,
        refresh_token=refresh,
        token_uri=db_creds.token_uri,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=db_creds.scopes
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save new access token
            db_creds.access_token = security.encrypt_data(creds.token)
            db.commit()
        except Exception as e:
            logging.error(f"Failed to refresh Google Token for user {user_id}: {e}")
            return None
            
    return creds

# --- API FACTORIES ---
def get_gmail_service(user_id: str, db: Session):
    creds = get_user_google_creds(user_id, db)
    return build('gmail', 'v1', credentials=creds) if creds else None

def get_drive_service(user_id: str, db: Session):
    creds = get_user_google_creds(user_id, db)
    return build('drive', 'v3', credentials=creds) if creds else None

def get_calendar_service(user_id: str, db: Session):
    creds = get_user_google_creds(user_id, db)
    return build('calendar', 'v3', credentials=creds) if creds else None

def get_sheets_service(user_id: str, db: Session):
    creds = get_user_google_creds(user_id, db)
    return build('sheets', 'v4', credentials=creds) if creds else None