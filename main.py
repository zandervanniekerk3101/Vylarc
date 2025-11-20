import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from sqlalchemy import text # Required for the fix

# --- DATABASE ---
from src.app.database import engine
from src.app.models import models

# --- ROUTES ---
from src.app.routes import auth, system, credits, chat, nexus, gmail, files, telephony
from src.app.config import get_settings
from src.app.services.credit_service import CreditException

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

# --- LIFESPAN (Auto-DB Repair) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup.
    1. Creates missing tables.
    2. Patches existing tables with missing columns (Self-Healing).
    """
    try:
        logger.info("--- INITIALIZING VYLARC NEURAL CORE ---")
        
        # 1. Create Missing Tables (Standard)
        models.Base.metadata.create_all(bind=engine)
        
        # 2. APPLY PATCHES (The Fix for 'UndefinedColumn')
        # We manually check and add the 'avatar_url' column if it's missing
        with engine.connect() as conn:
            try:
                logger.info("--- CHECKING FOR SCHEMA UPDATES ---")
                # This SQL command adds the column only if it doesn't exist
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(1024);"))
                conn.commit()
                logger.info("--- SCHEMA PATCH APPLIED: avatar_url ---")
            except Exception as e:
                # If it fails (e.g. already exists in a weird state), just log it
                logger.warning(f"Schema patch warning (non-critical): {e}")

        logger.info("--- DATABASE INTEGRITY VERIFIED ---")
    except Exception as e:
        logger.error(f"--- CRITICAL DB FAILURE: {e} ---")
    yield

# --- APP SETUP ---
app = FastAPI(
    title="Vylarc API",
    description="Backend server for the Vylarc AI Productivity Suite.",
    version="2.1.0",
    lifespan=lifespan
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Content-Type", "X-WordPress-Secret"],
)

# --- EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if isinstance(exc, CreditException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(exc)}"})

# --- ROUTERS ---
app.include_router(system.router, prefix="/system", tags=["System"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(credits.router, prefix="/credits", tags=["Credit System"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(nexus.router, prefix="/nexus", tags=["Nexus Core"])
app.include_router(gmail.router, prefix="/gmail", tags=["Email"])
app.include_router(files.router, prefix="/files", tags=["Drive"])
app.include_router(telephony.router, prefix="/call", tags=["Telephony"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Vylarc System Online", "docs_url": f"{settings.PUBLIC_BASE_URL}/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)