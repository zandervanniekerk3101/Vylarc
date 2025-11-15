import logging
import uuid
from datetime import timedelta

import requests
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.app import dependencies, models
from src.app.config import get_settings
from src.app.database import get_db_session
from src.app.schemas import user as user_schema
from src.app.schemas import token as token_schema
from src.app.schemas import core as core_schema
from src.app.utils import security

router = APIRouter()
settings = get_settings()

# --- Google OAuth2 Flow Setup ---
# These are the scopes required for Vylarc
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
    """Helper to create a Google OAuth Flow."""
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

# --- Standard Auth Routes (Email/Password) ---

@router.post(
    "/register", 
    response_model=user_schema.UserPublic, 
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user"
)
async def register_user(
    user_in: user_schema.UserCreate, 
    db: Session = Depends(dependencies.get_db)
):
    """
    Create a new user, hash their password, and create their
    initial credit balance.
    """
    hashed_password = security.get_password_hash(user_in.password)
    
    new_user = models.User(
        email=user_in.email.lower(),
        name=user_in.name,
        password_hash=hashed_password
    )
    
    # Create associated 1:1 tables
    new_user.credits = models.UserCredits(balance=0) # [cite: 173] Free tier starts with 0
    new_user.api_keys = models.UserApiKeys()
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register user.",
        )
        
    return new_user

@router.post("/login", response_model=token_schema.Token, summary="User login")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(dependencies.get_db)
):
    """
    Standard OAuth2 login. Takes username (email) and password.
    Returns a JWT.
    """
    user = db.query(models.User).filter(
        models.User.email == form_data.username.lower()
    ).first()
    
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# --- Google OAuth Routes ---

@router.get("/google/login", summary="Initiate Google OAuth flow")
async def google_login(request: Request):
    """
    Redirects the user to the Google consent screen.
    """
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline", 
        prompt="consent",
        include_granted_scopes="true"
    )
    
    # Store state in session or a temporary cache (not shown here)
    # For simplicity, we'll just redirect. A real app should store/check state.
    
    return Response(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={'Location': authorization_url})


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(request: Request, code: str, db: Session = Depends(dependencies.get_db)):
    """
    Handles the callback from Google.
    Exchanges the code for tokens, gets user info, creates or logs in the user,
    and returns a JWT.
    """
    flow = get_google_flow()
    
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logging.error(f"Error fetching Google token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google OAuth code.")
        
    credentials = flow.credentials
    
    # Get user info from the ID token
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        logging.error(f"Error verifying Google ID token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google ID token.")

    email = id_info.get("email")
    name = id_info.get("name")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email not returned from Google.")

    # --- Find or Create User ---
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    
    if not user:
        # User doesn't exist, create a new one
        # Note: No password, so they can *only* log in via Google
        user = models.User(
            email=email.lower(),
            name=name,
            password_hash=f"google-oauth-{uuid.uuid4()}" # Placeholder, not usable
        )
        user.credits = models.UserCredits(balance=0)
        user.api_keys = models.UserApiKeys()
        db.add(user)
    
    # --- Store OAuth Tokens ---
    # Encrypt tokens before storing [cite: 7, 115]
    encrypted_access = security.encrypt_data(credentials.token)
    encrypted_refresh = security.encrypt_data(credentials.refresh_token)
    
    expires_at = credentials.expiry if hasattr(credentials, 'expiry') else None

    # Find existing 'google' token or create a new one
    db_token = db.query(models.OAuthToken).filter(
        models.OAuthToken.user_id == user.id,
        models.OAuthToken.provider == "google"
    ).first()
    
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
        logging.error(f"Error saving user/token after Google auth: {e}")
        raise HTTPException(status_code=500, detail="Could not process Google login.")

    # --- Return Vylarc JWT ---
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    vylarc_jwt = security.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    # In a real app, you'd redirect to the frontend with the token
    # For an API, we can return it directly.
    return {"access_token": vylarc_jwt, "token_type": "bearer"}


# --- User Profile & Keys Routes ---

@router.get(
    "/me", 
    response_model=user_schema.UserProfile,
    summary="Get current user profile"
)
async def read_users_me(
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Returns the profile and credit balance for the authenticated user.
    """
    # Eager load credits
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    if not user.credits:
        # This should not happen if registration is correct, but as a fallback:
        user.credits = models.UserCredits(balance=0, user_id=user.id)
        db.add(user.credits)
        db.commit()
        db.refresh(user.credits)

    return {"user": user, "credits": user.credits}


@router.post(
    "/update-external-keys",
    response_model=user_schema.ApiKeysPublic,
    summary="Update user's external API keys (Twilio, ElevenLabs)"
)
async def update_external_keys(
    keys_in: user_schema.ApiKeysUpdate,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    [cite: 146]
    Updates and securely encrypts the user-provided API keys
    for Twilio and ElevenLabs.
    """
    api_keys = db.query(models.UserApiKeys).filter(
        models.UserApiKeys.user_id == current_user.id
    ).first()
    
    if not api_keys:
        # This shouldn't happen, but we can create it if missing
        api_keys = models.UserApiKeys(user_id=current_user.id)
        db.add(api_keys)
        
    update_data = keys_in.model_dump(exclude_unset=True)
    
    if "twilio_sid" in update_data:
        api_keys.twilio_sid = security.encrypt_data(update_data["twilio_sid"])
    if "twilio_auth_token" in update_data:
        api_keys.twilio_auth = security.encrypt_data(update_data["twilio_auth_token"])
    if "elevenlabs_key" in update_data:
        api_keys.elevenlabs_key = security.encrypt_data(update_data["elevenlabs_key"])
    if "elevenlabs_voice_id" in update_data:
        api_keys.elevenlabs_voice_id = update_data["elevenlabs_voice_id"]
        
    try:
        db.commit()
        db.refresh(api_keys)
    except Exception as e:
        db.rollback()
        logging.error(f"Error updating API keys: {e}")
        raise HTTPException(status_code=500, detail="Could not update API keys.")

    return {
        "has_twilio": api_keys.twilio_sid is not None,
        "has_elevenlabs": api_keys.elevenlabs_key is not None,
        "elevenlabs_voice_id": api_keys.elevenlabs_voice_id,
        "updated_at": api_keys.updated_at
    }