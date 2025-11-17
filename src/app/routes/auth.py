import logging
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow

from src.app import dependencies, models
from src.app.config import get_settings
from src.app.database import get_db_session
from src.app.schemas import user as user_schema
from src.app.schemas import token as token_schema
from src.app.schemas import core as core_schema
from src.app.utils import security

router = APIRouter()
settings = get_settings()

# --------------------------
# GOOGLE OAUTH2 FLOW SETUP
# --------------------------
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
    """
    Helper to create a Google OAuth Flow.
    """
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

# --------------------------
# HELPER: SET COOKIE
# --------------------------
def set_vylarc_cookie(response: Response, token: str):
    """
    Sets the vylarc_session cookie for SSO across all platforms.
    """
    response.set_cookie(
        key="vylarc_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

# --------------------------
# EMAIL / PASSWORD AUTH
# --------------------------
@router.post(
    "/register",
    response_model=user_schema.UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(user_in: user_schema.UserCreate, db: Session = Depends(dependencies.get_db)):
    """
    Registers a new user with hashed password, initializes credits & API keys.
    """
    hashed_password = security.get_password_hash(user_in.password)

    new_user = models.User(
        email=user_in.email.lower(),
        name=user_in.name,
        password_hash=hashed_password,
    )

    # 1:1 related tables
    new_user.credits = models.UserCredits(balance=0)
    new_user.api_keys = models.UserApiKeys()

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    except Exception as e:
        db.rollback()
        logging.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Could not register user.")

    return new_user


@router.post("/login", summary="User login")
async def login_user(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(dependencies.get_db)
):
    """
    Login with email/password. Returns JWT and sets vylarc_session cookie.
    """
    user = db.query(models.User).filter(models.User.email == form_data.username.lower()).first()
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = security.create_access_token(
        {"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    set_vylarc_cookie(response, access_token)

    return {"access_token": access_token, "token_type": "bearer"}

# --------------------------
# GOOGLE OAUTH ROUTES
# --------------------------
@router.get("/google/login", summary="Initiate Google OAuth login")
async def google_login():
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return Response(status_code=307, headers={"Location": authorization_url})


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(
    request: Request, response: Response, code: str, db: Session = Depends(dependencies.get_db)
):
    flow = get_google_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logging.error(f"Google token fetch error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google OAuth code")

    credentials = flow.credentials

    # Decode ID token
    try:
        id_info = id_token.verify_oauth2_token(credentials.id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError as e:
        logging.error(f"Google ID token error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google ID token")

    email = id_info.get("email")
    name = id_info.get("name")
    if not email:
        raise HTTPException(status_code=400, detail="Email not returned from Google")

    # --------------------------
    # FIND OR CREATE USER
    # --------------------------
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user:
        user = models.User(
            email=email.lower(),
            name=name,
            password_hash=f"google-oauth-{uuid.uuid4()}"  # unusable password
        )
        user.credits = models.UserCredits(balance=0)
        user.api_keys = models.UserApiKeys()
        db.add(user)

    # --------------------------
    # STORE OAUTH TOKENS
    # --------------------------
    encrypted_access = security.encrypt_data(credentials.token)
    encrypted_refresh = security.encrypt_data(credentials.refresh_token)
    expires_at = getattr(credentials, "expiry", None)

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
            expires_at=expires_at,
        )
        db.add(db_token)

    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        logging.error(f"Google login DB commit error: {e}")
        raise HTTPException(status_code=500, detail="Could not process Google login")

    # --------------------------
    # RETURN JWT & COOKIE
    # --------------------------
    access_token = security.create_access_token(
        {"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    set_vylarc_cookie(response, access_token)
    return {"access_token": access_token, "token_type": "bearer"}

# --------------------------
# USER PROFILE & CREDITS
# --------------------------
@router.get("/me", response_model=user_schema.UserProfile, summary="Current user profile")
async def get_current_user_profile(
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Returns user profile, credits & API keys.
    """
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.credits:
        user.credits = models.UserCredits(balance=0, user_id=user.id)
        db.add(user.credits)
        db.commit()
        db.refresh(user.credits)

    return {"user": user, "credits": user.credits}

# --------------------------
# UPDATE EXTERNAL API KEYS
# --------------------------
@router.post("/update-external-keys", response_model=user_schema.ApiKeysPublic, summary="Update external API keys")
async def update_external_keys(
    keys_in: user_schema.ApiKeysUpdate,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db),
):
    api_keys = db.query(models.UserApiKeys).filter(models.UserApiKeys.user_id == current_user.id).first()
    if not api_keys:
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
        raise HTTPException(status_code=500, detail="Could not update API keys")

    return {
        "has_twilio": api_keys.twilio_sid is not None,
        "has_elevenlabs": api_keys.elevenlabs_key is not None,
        "elevenlabs_voice_id": api_keys.elevenlabs_voice_id,
        "updated_at": api_keys.updated_at,
    }

# --------------------------
# LOGOUT
# --------------------------
@router.post("/logout", summary="Logout user")
async def logout(response: Response):
    """
    Deletes vylarc_session cookie to log user out.
    """
    response.delete_cookie("vylarc_session")
    return {"detail": "Logged out successfully"}
