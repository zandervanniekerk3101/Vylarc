import logging
from fastapi import Depends, HTTPException, status, Cookie
from sqlalchemy.orm import Session

from src.app.database import get_db_session
from src.app import models
from src.app.utils import security

# --- DB SESSION ---
def get_db() -> Session:
    """
    Provides a SQLAlchemy database session.
    Use as Depends(get_db) in routers.
    """
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


# --- CURRENT USER DEPENDENCY ---
def get_current_user(
    vylarc_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Extracts current user from vylarc_session cookie (JWT).
    Returns User model or raises 401 if not logged in.
    """
    if not vylarc_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not logged in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = security.decode_access_token(vylarc_session)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload["sub"]
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user


# --- CURRENT ADMIN (OPTIONAL) ---
def get_current_admin(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """
    Checks if current user has admin rights.
    Raises 403 if not.
    """
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user


# --- OPTIONAL: CURRENT USER OR NONE ---
def get_optional_user(
    vylarc_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
) -> models.User | None:
    """
    Returns user if logged in, otherwise None.
    Useful for endpoints that allow both guests and users.
    """
    if not vylarc_session:
        return None
    payload = security.decode_access_token(vylarc_session)
    if not payload or "sub" not in payload:
        return None
    user_id = payload["sub"]
    return db.query(models.User).filter(models.User.id == int(user_id)).first()
