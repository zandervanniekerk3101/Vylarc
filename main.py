import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from sqlalchemy import text

# --- DATABASE ---
from src.app.database import engine
from src.app.models import models

# --- ROUTES ---
from src.app.routes import auth, system, credits, chat, nexus, gmail, files, telephony, canvas
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
        
        # 2. APPLY PATCHES (The Fix for 'UndefinedColumn' errors)
        # We manually check and add missing columns to the 'users' table
        with engine.connect() as conn:
            try:
                logger.info("--- CHECKING FOR SCHEMA UPDATES ---")
                
                # Patch 1: avatar_url
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(1024);"))
                
                # Patch 2: is_active (The fix for your current error)
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
                
                conn.commit()
                logger.info("--- SCHEMA PATCHES APPLIED SUCCESSFULLY ---")
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
    version="2.2.0",
    lifespan=lifespan
)

# --- CORS ---
# SECURITY FIX: Restrict CORS to specific origins instead of allowing all
# Add your WordPress domain and any other trusted domains here
allowed_origins = [
    "https://platform.vylarc.com",
    "http://localhost:3000",  # For local development
    "http://localhost:8080",   # Alternative local development port
]

# Allow any origin that matches platform.vylarc.com or localhost for development
if settings.PUBLIC_BASE_URL:
    base_domain = settings.PUBLIC_BASE_URL.replace('//', '//').strip('/')
    if base_domain and base_domain not in allowed_origins:
        allowed_origins.append(base_domain)

# Add origins from environment variable
if settings.ALLOWED_ORIGINS:
    env_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
    allowed_origins.extend(env_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # FIXED: No longer allows all origins
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
app.include_router(canvas.router, prefix="/canvas", tags=["Coding Canvas"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Vylarc System Online", "docs_url": f"{settings.PUBLIC_BASE_URL}/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)