import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# We need Starlette's exception to catch default FastAPI errors
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.app.routes import auth, system, credits, chat
from src.app.config import get_settings
# Import your custom credit exception
from src.app.services.credit_service import CreditException

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- SETTINGS ---
settings = get_settings()

# --- APP ---
app = FastAPI(
    title="Vylarc API",
    description="Backend server for the Vylarc AI Productivity Suite.",
    version="1.0.0",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GLOBAL EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 1. Allow standard HTTP Exceptions (404, 409, 422, etc.) to pass through
    # This fixes the issue where "Email already exists" becomes "Internal Server Error"
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
        
    # 2. Handle Vylarc Credit Exceptions (Payment Required)
    if isinstance(exc, CreditException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # 3. Log and mask ACTUAL Server Crashes
    # If we get here, it's a real crash (code bug).
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"}, # Temporary: show the error to help you debug
    )

# --- ROUTERS ---
app.include_router(system.router, prefix="/system", tags=["System"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(credits.router, prefix="/credits", tags=["Credit System"])
app.include_router(chat.router, prefix="/chat", tags=["Chat System (ChatGPT)"])

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