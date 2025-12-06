import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, EmailStr
import requests

from src.app import models, dependencies
from src.app.config import get_settings
from src.app.schemas import user as user_schema
from src.app.schemas import token as token_schema
from src.app.utils import security

router = APIRouter()
settings = get_settings()

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

# --- Google Sign-In ---
class GoogleSignInPayload(BaseModel):
    id_token: str
    name: str | None = None


@router.post("/google", response_model=token_schema.Token)
async def google_login(
    payload: GoogleSignInPayload,
    db: Session = Depends(dependencies.get_db),
):
    """
    Accepts a Google ID Token from the mobile app, verifies it with Google,
    upserts a local user, and returns a Vylarc JWT.
    """
    try:
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": payload.id_token},
            timeout=10,
        )
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Failed to verify token with Google")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    data = resp.json()
    aud = data.get("aud")
    email = data.get("email")
    email_verified_raw = data.get("email_verified")
    email_verified = str(email_verified_raw).lower() in ("true", "1", "yes")
    issuer = data.get("iss")

    allowed_audiences = [
        a.strip() for a in (settings.GOOGLE_OAUTH_CLIENT_IDS or "").split(",") if a.strip()
    ]

    if allowed_audiences and aud not in allowed_audiences:
        raise HTTPException(status_code=401, detail="Invalid token audience")

    if issuer not in {"https://accounts.google.com", "accounts.google.com"}:
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    if not email or not email_verified:
        raise HTTPException(status_code=401, detail="Email not verified with Google")

    # Upsert user
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user:
        # Use a generated password; logins will be through Google
        generated_pw = f"google-{data.get('sub') or email}"
        user = models.User(
            email=email.lower(),
            name=data.get("name") or payload.name,
            password_hash=security.get_password_hash(generated_pw),
        )
        user.credits = models.UserCredits(balance=0)
        user.api_keys = models.UserApiKeys()
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(models.User).filter(models.User.email == email.lower()).first()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create user: {e}")

    access_token = security.create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}