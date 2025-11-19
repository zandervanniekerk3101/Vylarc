from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import requests # Using direct HTTP to avoid heavy Twilio lib dependency if desired

from src.app import dependencies, models
from src.app.utils import security

router = APIRouter()

class CallRequest(BaseModel):
    to_number: str
    message: str

@router.post("/initiate", summary="Make a Call")
async def initiate_call(
    payload: CallRequest,
    user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    # 1. Get Keys
    keys = db.query(models.UserApiKeys).filter(models.UserApiKeys.user_id == user.id).first()
    if not keys or not keys.twilio_sid or not keys.twilio_auth:
        raise HTTPException(400, "Twilio Keys not configured in Settings.")

    sid = security.decrypt_data(keys.twilio_sid)
    auth = security.decrypt_data(keys.twilio_auth)

    # 2. Call Twilio API
    # Note: TwiML would be needed here to actually say the message. 
    # For now, we trigger the call.
    tw_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    
    try:
        # Using Vylarc default voice TwiML bin or generating one
        # This is a simplified example
        data = {
            "To": payload.to_number,
            "From": "+15005550006", # User must add their Twilio number in settings in real app
            "Url": "http://demo.twilio.com/docs/voice.xml" # Placeholder TwiML
        }
        
        resp = requests.post(tw_url, data=data, auth=(sid, auth))
        
        if resp.status_code >= 400:
            raise HTTPException(400, f"Twilio Error: {resp.text}")
            
        return {"status": "calling", "sid": resp.json().get("sid")}
        
    except Exception as e:
        raise HTTPException(500, f"Call Failed: {str(e)}")