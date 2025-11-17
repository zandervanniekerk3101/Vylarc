import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# --- UPDATED IMPORTS ---
from src.app.routes import auth, system, credits, chat
from src.app.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load settings
settings = get_settings()

app = FastAPI(
    title="Vylarc API",
    description="Backend server for the Vylarc AI Productivity Suite.",
    version="1.0.0",
)

# --- MIDDLEWARE (THIS IS THE CORS FIX) ---

# Define the origins that are allowed to make requests
origins = [
    "https://vylarc.onrender.com", # The server itself
    "https://vylarc.com",         # Your main website
    "http://vylarc.com",          # Your website (non-https)
    "http://localhost",           # For local testing
    "http://localhost:8000",      # For local testing
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Use our specific list
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- END FIX ---


# --- Global Exception Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    # Import here to avoid circular dependency
    try:
        from src.app.services.credit_service import CreditException
        if isinstance(exc, CreditException):
            # Handle 402 errors specifically
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
    except ImportError:
        pass # Handle cases where CreditException might not be defined yet
    
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )

# --- API Routers ---
app.include_router(system.router, prefix="/system", tags=["System"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# --- PHASE 2 ---
app.include_router(credits.router, prefix="/credits", tags=["Credit System"])
app.include_router(chat.router, prefix="/chat", tags=["Chat System (ChatGPT)"])


# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def read_root():
    """
    Root endpoint for the Vylarc API.
    """
    return {
        "message": "Welcome to the Vylarc API",
        "docs_url": f"{settings.PUBLIC_BASE_URL}/docs",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)