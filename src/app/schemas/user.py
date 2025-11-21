from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime

# --- User Schemas ---

class UserBase(BaseModel):
    email: EmailStr
    name: str | None = None

class UserCreate(UserBase):
    password: str

class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Credits Schema ---

class UserCreditsPublic(BaseModel):
    balance: int
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Full User Profile ---

class UserProfile(BaseModel):
    user: UserPublic
    credits: UserCreditsPublic

# --- API Keys Schemas ---

class ApiKeysUpdate(BaseModel):
    twilio_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_number: str | None = None
    elevenlabs_key: str | None = None
    elevenlabs_voice_id: str | None = None

class ApiKeysPublic(BaseModel):
    has_twilio: bool
    has_elevenlabs: bool
    elevenlabs_voice_id: str | None = None
    updated_at: datetime

    class Config:
        from_attributes = True