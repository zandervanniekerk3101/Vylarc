import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

# --- IMPORTS FOR DB AUTO-INIT ---
from src.app.database import engine
from src.app.models import models
# --------------------------------

# --- ROUTES ---
from src.app.routes import auth, system, credits, chat, nexus
from src.app.config import get_settings
from src.app.services.credit_service import CreditException

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# --- LIFESPAN (Auto-Create Tables) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup.
    Forces the creation of all database tables if they don't exist.
    This ensures the new 'projects' and 'map_pins' tables are created immediately.
    """
    try:
        logger.info("--- CHECKING DATABASE TABLES ---")
        models.Base.metadata.create_all(bind=engine)
        logger.info("--- DATABASE TABLES VERIFIED/CREATED SUCCESSFULLY ---")
    except Exception as e:
        logger.error(f"--- DATABASE INIT FAILED: {e} ---")
    yield

# --- APP ---
app = FastAPI(
    title="Vylarc API",
    description="Backend server for the Vylarc AI Productivity Suite.",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS (CRITICAL FOR FRONTEND CONNECTIVITY) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Content-Type", "X-WordPress-Secret"],
)

# --- EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Pass through standard HTTP exceptions (404, 401, etc)
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    # Pass through Vylarc Credit exceptions
    if isinstance(exc, CreditException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # Log unexpected crashes
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
    )

# --- REGISTER ROUTERS ---
app.include_router(system.router, prefix="/system", tags=["System"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(credits.router, prefix="/credits", tags=["Credit System"])
app.include_router(chat.router, prefix="/chat", tags=["Chat System (ChatGPT)"])
app.include_router(nexus.router, prefix="/nexus", tags=["Vylarc Nexus"]) # Code Canvas & Maps

# --- ROOT ---
@app.get("/", tags=["Root"])
async def read_root():
    return {
        "message": "Welcome to the Vylarc API",
        "docs_url": f"{settings.PUBLIC_BASE_URL}/docs",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)