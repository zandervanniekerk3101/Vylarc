# src/init_db.py
import logging
import sys
import os

# Add the project root to the Python path so imports work
sys.path.append(os.getcwd())

from src.app.database import engine
from src.app.models import models

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    """
    Force-create tables based on models.py.
    This ignores Alembic migrations and just builds the schema directly.
    """
    print("--- INITIALIZING DATABASE ---")
    try:
        # This command looks at all models (User, UserCredits, etc.)
        # and creates the table if it doesn't exist.
        models.Base.metadata.create_all(bind=engine)
        print("--- TABLES CREATED SUCCESSFULLY ---")
    except Exception as e:
        print(f"--- ERROR CREATING TABLES: {e} ---")
        logger.error(f"Database init failed: {e}")

if __name__ == "__main__":
    init_db()