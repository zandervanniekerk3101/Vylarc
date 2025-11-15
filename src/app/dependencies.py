import uuid
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.app.database import get_db_session
from src.app.models import models
from src.app.utils import security
from src.app.schemas import token as token_schema

# --- Database Dependency ---

def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get a database session.
    """
    with get_db_session() as session:
        yield session

# --- Auth Dependency ---

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> models.User:
    """
    Dependency to get the current authenticated user from a JWT.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = security.decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
        
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    token_data = token_schema.TokenData(user_id=user_id)
    
    user = db.get(models.User, token_data.user_id)
    
    if user is None:
        raise credentials_exception
        
    return user