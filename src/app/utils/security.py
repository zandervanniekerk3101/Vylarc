import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.responses import Response

from src.app.config import get_settings

settings = get_settings()

# --- PASSWORD HASHING ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
BCRYPT_MAX_BYTES = 72

def _truncate_password(password: str) -> str:
    """
    Safely truncate a password to bcrypt's 72-byte limit
    without breaking multi-byte characters.
    """
    b = password.encode("utf-8")
    if len(b) <= BCRYPT_MAX_BYTES:
        return password
    truncated = b[:BCRYPT_MAX_BYTES]
    while True:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]

def get_password_hash(password: str) -> str:
    """
    Hash a password, safely truncating it to 72 bytes for bcrypt.
    """
    safe_password = _truncate_password(password)
    if safe_password != password:
        logging.warning("Password truncated to 72 bytes for bcrypt compatibility.")
    return pwd_context.hash(safe_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_truncate_password(plain_password), hashed_password)

# --- JWT ---
SECRET_KEY = settings.FLASK_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    for key, value in to_encode.items():
        if isinstance(value, uuid.UUID):
            to_encode[key] = str(value)
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logging.warning(f"JWT Error: {e}")
        return None

# --- COOKIE SSO HELPER ---
def set_auth_cookie(response: Response, token: str, max_age_minutes: int = 60*24):
    response.set_cookie(
        key="vylarc_session",
        value=token,
        max_age=max_age_minutes*60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

# --- AES ENCRYPTION FOR API KEYS ---
try:
    key_material = bytes.fromhex(settings.ENCRYPTION_KEY)
    if len(key_material) < 32:
        raise ValueError("ENCRYPTION_KEY must be at least 32 bytes (64 hex chars)")

    salt = b'vylarc_static_salt'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    fernet_key = base64.urlsafe_b64encode(kdf.derive(key_material))
    cipher_suite = Fernet(fernet_key)
    logging.info("Security cipher suite initialized successfully.")
except Exception as e:
    logging.critical(f"Failed to initialize encryption cipher: {e}")
    cipher_suite = None

def encrypt_data(data: str | None) -> str | None:
    if data is None or cipher_suite is None:
        return None
    try:
        return cipher_suite.encrypt(data.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logging.error(f"Encryption failed: {e}")
        return None

def decrypt_data(encrypted_data: str | None) -> str | None:
    if encrypted_data is None or cipher_suite is None:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logging.warning(f"Decryption failed: {e}")
        return None
