import logging
import uuid
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Header
from fastapi.security import OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, EmailStr

from src.app import models, dependencies
from src.app.config import get_settings
from src.app.schemas import user as user_schema
from src.app.schemas import token as token_schema
from src.app.utils import security

# --- CRITICAL FIX: Allow Google to expand scopes without crashing ---
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
# ------------------------------------------------------------------

router = APIRouter()
settings = get_settings()

# --- Google OAuth2 Flow Setup ---
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/forms",
]

def get_google_flow() -> Flow:
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GOOGLE_SCOPES,
        redirect_uri=settings.FULL_GOOGLE_REDIRECT_URI,
    )

# --- Standard Auth Routes ---
@router.post("/register", response_model=user_schema.UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: user_schema.UserCreate, db: Session = Depends(dependencies.get_db)):
    if not user_in.password or len(user_in.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters long.")
    
    hashed_password = security.get_password_hash(user_in.password)

    new_user = models.User(
        email=user_in.email.lower(),
        name=user_in.name,
        password_hash=hashed_password
    )
    # Create Relations
    new_user.credits = models.UserCredits(balance=0)
    new_user.api_keys = models.UserApiKeys()

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered.")
    except Exception as e:
        db.rollback()
        logging.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Could not register user.")
    return new_user

@router.post("/login", response_model=token_schema.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(dependencies.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username.lower()).first()
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(data={"sub": str(user.id)}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- User Info ---
@router.get("/me", response_model=user_schema.UserProfile)
async def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    return {"user": current_user, "credits": current_user.credits}

# --- API KEYS CONFIGURATION ---
@router.post("/update-external-keys", response_model=user_schema.ApiKeysPublic)
async def update_external_keys(
    keys_in: user_schema.ApiKeysUpdate,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    api_keys = db.query(models.UserApiKeys).filter(models.UserApiKeys.user_id == current_user.id).first()
    
    if not api_keys:
        api_keys = models.UserApiKeys(user_id=current_user.id)
        db.add(api_keys)
        
    if keys_in.twilio_sid:
        api_keys.twilio_sid = security.encrypt_data(keys_in.twilio_sid)
    if keys_in.twilio_auth_token:
        api_keys.twilio_auth = security.encrypt_data(keys_in.twilio_auth_token)
    if keys_in.elevenlabs_key:
        api_keys.elevenlabs_key = security.encrypt_data(keys_in.elevenlabs_key)
    if keys_in.elevenlabs_voice_id:
        api_keys.elevenlabs_voice_id = keys_in.elevenlabs_voice_id
        
    try:
        db.commit()
        db.refresh(api_keys)
    except Exception as e:
        db.rollback()
        logging.error(f"Key update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save keys.")
    
    return {
        "has_twilio": api_keys.twilio_sid is not None,
        "has_elevenlabs": api_keys.elevenlabs_key is not None,
        "elevenlabs_voice_id": api_keys.elevenlabs_voice_id,
        "updated_at": api_keys.updated_at
    }

# --- Google OAuth Routes ---
@router.get("/google/login")
async def google_login(request: Request):
    flow = get_google_flow()
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return Response(status_code=307, headers={"Location": auth_url})

@router.get("/google/callback")
async def google_callback(request: Request, code: str, db: Session = Depends(dependencies.get_db)):
    flow = get_google_flow()
    try:
        # The os.environ setting at the top prevents crash on scope change
        flow.fetch_token(code=code)
    except Exception as e:
        logging.error(f"Google fetch token error: {e}")
        # Log the specific error to help debugging but don't crash the whole app
        raise HTTPException(status_code=400, detail="Invalid Google OAuth code or Scope Mismatch.")

    credentials = flow.credentials
    try:
        id_info = id_token.verify_oauth2_token(credentials.id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError as e:
        logging.error(f"Google ID token verification error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google ID token.")

    email = id_info.get("email")
    name = id_info.get("name")
    if not email:
        raise HTTPException(status_code=400, detail="Email not returned from Google.")

    # Find or Create User
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user:
        user = models.User(
            email=email.lower(),
            name=name,
            password_hash=f"google-oauth-{uuid.uuid4()}"
        )
        user.credits = models.UserCredits(balance=0)
        user.api_keys = models.UserApiKeys()
        db.add(user)

    # Store OAuth Tokens
    encrypted_access = security.encrypt_data(credentials.token)
    encrypted_refresh = security.encrypt_data(credentials.refresh_token)
    expires_at = getattr(credentials, "expiry", None)

    # Upsert OAuthToken Record
    db_token = db.query(models.OAuthToken).filter(models.OAuthToken.user_id == user.id, models.OAuthToken.provider == "google").first()
    if db_token:
        db_token.access_token = encrypted_access
        db_token.refresh_token = encrypted_refresh
        db_token.expires_at = expires_at
    else:
        db_token = models.OAuthToken(
            user_id=user.id, 
            provider="google", 
            access_token=encrypted_access, 
            refresh_token=encrypted_refresh, 
            expires_at=expires_at
        )
        db.add(db_token)

    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        logging.error(f"Google login commit error: {e}")
        raise HTTPException(status_code=500, detail="Could not process Google login.")

    # Generate Vylarc JWT
    vylarc_jwt = security.create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    
    # Redirect back to WordPress
    redirect_url = f"{settings.PUBLIC_BASE_URL.replace('api.', '')}?vylarc_token={vylarc_jwt}"
    
    if "localhost" in settings.PUBLIC_BASE_URL:
        redirect_url = f"http://localhost:3000?vylarc_token={vylarc_jwt}"
        
    return Response(status_code=307, headers={"Location": redirect_url})

# --- WordPress Bridge ---
class WpLoginPayload(BaseModel):
    email: EmailStr
    name: str | None = None

@router.post("/wp_login", response_model=token_schema.Token)
async def wp_login(payload: WpLoginPayload, x_wordpress_secret: str = Header(None), db: Session = Depends(dependencies.get_db)):
    if x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        raise HTTPException(403, "Invalid Secret")
    
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user:
        hashed_password = security.get_password_hash(f"wp-sso-{uuid.uuid4()}")
        user = models.User(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hashed_password
        )
        user.credits = models.UserCredits(balance=0)
        user.api_keys = models.UserApiKeys()
        db.add(user)
        db.commit()
    
    token = security.create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}