import logging
from uuid import UUID
from twilio.rest import Client
from sqlalchemy.orm import Session
from fastapi import HTTPException

from src.app.models import models
from src.app.utils import security
from src.app.config import get_settings

settings = get_settings()

def get_user_twilio_client(db: Session, user_id: UUID):
    """
    Retrieves the Twilio Client and Phone Number for a specific user.
    """
    api_keys = db.query(models.UserApiKeys).filter(models.UserApiKeys.user_id == user_id).first()
    
    if not api_keys or not api_keys.twilio_sid or not api_keys.twilio_auth:
        raise HTTPException(status_code=400, detail="Twilio credentials not found. Please add them in settings.")
        
    if not api_keys.twilio_number:
        raise HTTPException(status_code=400, detail="Twilio phone number not found. Please add it in settings.")

    sid = security.decrypt_data(api_keys.twilio_sid)
    token = security.decrypt_data(api_keys.twilio_auth)
    number = api_keys.twilio_number
    
    try:
        client = Client(sid, token)
        return client, number
    except Exception as e:
        logging.error(f"Failed to create Twilio client for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Invalid Twilio credentials.")

def make_call(db: Session, user_id: UUID, to_number: str, message_text: str):
    """
    Initiates a call using the user's own credentials.
    """
    client, from_number = get_user_twilio_client(db, user_id)
    
    # Construct TwiML URL (this endpoint must exist on your server)
    # We encode the message into the URL so the TwiML endpoint knows what to say
    import urllib.parse
    encoded_message = urllib.parse.quote(message_text)
    twiml_url = f"{settings.PUBLIC_BASE_URL}/call/twiml?message={encoded_message}"
    
    try:
        call = client.calls.create(
            to=to_number,
            from_=from_number, # <--- USES USER'S NUMBER
            url=twiml_url
        )
        return call.sid
    except Exception as e:
        logging.error(f"Twilio call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Twilio Call Failed: {str(e)}")