from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import logging

from src.app.config import get_settings

settings = get_settings()

try:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600, # Recycle connections every hour
    )
    
    SessionLocal = sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=engine
    )
    
    logging.info("Database engine created successfully.")

except Exception as e:
    logging.error(f"Failed to create database engine: {e}")
    raise

@contextmanager
def get_db_session():
    """
    Provides a transactional scope around a series of operations.
    Handles session creation, commit, and rollback.
    """
    db: Session | None = None
    try:
        db = SessionLocal()
        yield db
    except Exception:
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()