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

from src.app.config import get_settings

settings = get_settings()

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)

# --- JWT Token Handling ---
SECRET_KEY = settings.FLASK_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates a new JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    # Convert UUID to string if present
    for key, value in to_encode.items():
        if isinstance(value, uuid.UUID):
            to_encode[key] = str(value)
            
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decodes a JWT token and returns its payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logging.warning(f"JWT Error: {e}")
        return None

# --- AES Encryption for API Keys ---
# We derive a 32-byte key from the user's ENCRYPTION_KEY for Fernet
# This is more robust than assuming the key is already base64-encoded.
try:
    key_material = bytes.fromhex(settings.ENCRYPTION_KEY)
    if len(key_material) < 32:
        raise ValueError("ENCRYPTION_KEY must be at least 32 bytes (64 hex chars)")
    
    # Use a static salt, as we want the key to be deterministic from the env var
    salt = b'vylarc_static_salt' 
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    fernet_key = base6f.urlsafe_b64encode(kdf.derive(key_material))
    cipher_suite = Fernet(fernet_key)
    logging.info("Security cipher suite initialized successfully.")
except Exception as e:
    logging.critical(f"FATAL: Failed to initialize encryption cipher: {e}")
    logging.critical("Ensure ENCRYPTION_KEY is a 32-byte hex string.")
    cipher_suite = None # This will cause encryption to fail safely

def encrypt_data(data: str | None) -> str | None:
    """Encrypts a string using the application's secret key."""
    if data is None or cipher_suite is None:
        return None
    try:
        encrypted_bytes = cipher_suite.encrypt(data.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        logging.error(f"Encryption failed: {e}")
        return None

def decrypt_data(encrypted_data: str | None) -> str | None:
    """Decrypts a string using the application's secret key."""
    if encrypted_data is None or cipher_suite is None:
        return None
    try:
        decrypted_bytes = cipher_suite.decrypt(encrypted_data.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        # This includes InvalidToken, which is expected if data is tampered/corrupt
        logging.warning(f"Decryption failed: {e}")
        return None