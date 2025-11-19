import logging
import uuid
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

router = APIRouter()
settings = get_settings()

# --- Google OAuth2 Flow ---
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

# --- Helper: Truncate password safely to 72 bytes ---
def safe_truncate_password(password: str) -> str:
    b = password.encode("utf-8")
    if len(b) > 72:
        # Truncate to 72 bytes without breaking multi-byte characters
        truncated = b[:72]
        while True:
            try:
                return truncated.decode("utf-8")
            except UnicodeDecodeError:
                truncated = truncated[:-1]
    return password

# --- Standard Auth Routes ---
@router.post("/register", response_model=user_schema.UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: user_schema.UserCreate, db: Session = Depends(dependencies.get_db)):
    if not user_in.password or len(user_in.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters long.")
    
    password_safe = safe_truncate_password(user_in.password)
    hashed_password = security.get_password_hash(password_safe)

    new_user = models.User(
        email=user_in.email.lower(),
        name=user_in.name,
        password_hash=hashed_password,
        credits=models.UserCredits(balance=0),
        api_keys=models.UserApiKeys()
    )
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
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    password_safe = safe_truncate_password(form_data.password)
    if not security.verify_password(password_safe, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(data={"sub": str(user.id)}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- Google OAuth Routes ---
@router.get("/google/login")
async def google_login(request: Request):
    flow = get_google_flow()
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return Response(status_code=307, headers={"Location": auth_url})

@router.get("/google/callback")
async def google_callback(request: Request, code: str, db: Session = Depends(dependencies.get_db)):
    flow = get_google_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logging.error(f"Google fetch token error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google OAuth code.")

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

    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user:
        user = models.User(
            email=email.lower(),
            name=name,
            password_hash=f"google-oauth-{uuid.uuid4()}",
            credits=models.UserCredits(balance=0),
            api_keys=models.UserApiKeys()
        )
        db.add(user)

    encrypted_access = security.encrypt_data(credentials.token)
    encrypted_refresh = security.encrypt_data(credentials.refresh_token)
    expires_at = getattr(credentials, "expiry", None)

    db_token = db.query(models.OAuthToken).filter(models.OAuthToken.user_id == user.id, models.OAuthToken.provider == "google").first()
    if db_token:
        db_token.access_token = encrypted_access
        db_token.refresh_token = encrypted_refresh
        db_token.expires_at = expires_at
    else:
        db_token = models.OAuthToken(user_id=user.id, provider="google", access_token=encrypted_access, refresh_token=encrypted_refresh, expires_at=expires_at)
        db.add(db_token)

    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        logging.error(f"Google login commit error: {e}")
        raise HTTPException(status_code=500, detail="Could not process Google login.")

    vylarc_jwt = security.create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": vylarc_jwt, "token_type": "bearer"}

# --- User Info ---
@router.get("/me", response_model=user_schema.UserProfile)
async def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    return {"user": current_user, "credits": current_user.credits}

# --- WordPress Bridge ---
class WpLoginPayload(BaseModel):
    email: EmailStr
    name: str | None = None

@router.post("/wp_login", response_model=token_schema.Token, summary="WordPress Bridge Login")
async def wordpress_sso_login(payload: WpLoginPayload, x_wordpress_secret: str = Header(None), db: Session = Depends(dependencies.get_db)):
    if not x_wordpress_secret or x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        logging.warning("Invalid or missing X-WordPress-Secret")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret key.")

    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()

    if not user:
        logging.info(f"Auto-provisioning new Vylarc user from WP: {payload.email}")
        hashed_password = security.get_password_hash(safe_truncate_password(f"wp-sso-{uuid.uuid4()}"))
        user = models.User(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hashed_password,
            credits=models.UserCredits(balance=0),
            api_keys=models.UserApiKeys()
        )
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
        except Exception as e:
            db.rollback()
            logging.error(f"WP-SSO Auto-provisioning error: {e}")
            raise HTTPException(status_code=500, detail="Could not create user account.")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(data={"sub": str(user.id)}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}
