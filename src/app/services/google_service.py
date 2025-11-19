import logging
from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.app.models import models
from src.app.utils import security
from src.app.config import get_settings

settings = get_settings()

def get_creds(user_id: str, db: Session) -> Credentials | None:
    """
    Retrieves and automatically refreshes Google Credentials.
    Reads from the OAuthToken table where provider='google'.
    """
    # 1. Get User's OAuth Token (Aligned with auth.py)
    token_record = db.query(models.OAuthToken).filter(
        models.OAuthToken.user_id == user_id,
        models.OAuthToken.provider == "google"
    ).first()
    
    if not token_record or not token_record.refresh_token:
        logging.warning(f"No Google credentials found for user {user_id}")
        return None

    # 2. Decrypt
    access_token = security.decrypt_data(token_record.access_token)
    refresh_token = security.decrypt_data(token_record.refresh_token)

    if not refresh_token:
        logging.error(f"Failed to decrypt refresh token for user {user_id}")
        return None

    # 3. Build Credentials Object
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        # These scopes must match what was requested in auth.py
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send", 
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
    )

    # 4. Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            logging.info(f"Refreshing Google Token for {user_id}...")
            creds.refresh(Request())
            
            # Save new access token back to DB
            token_record.access_token = security.encrypt_data(creds.token)
            db.commit()
            
        except Exception as e:
            logging.error(f"Failed to refresh Google Token: {e}")
            return None
            
    return creds

# --- API SERVICE FACTORIES ---

def get_gmail_service(user_id: str, db: Session):
    creds = get_creds(user_id, db)
    return build('gmail', 'v1', credentials=creds) if creds else None

def get_drive_service(user_id: str, db: Session):
    creds = get_creds(user_id, db)
    return build('drive', 'v3', credentials=creds) if creds else None

def get_calendar_service(user_id: str, db: Session):
    creds = get_creds(user_id, db)
    return build('calendar', 'v3', credentials=creds) if creds else None

def get_sheets_service(user_id: str, db: Session):
    creds = get_creds(user_id, db)
    return build('sheets', 'v4', credentials=creds) if creds else None