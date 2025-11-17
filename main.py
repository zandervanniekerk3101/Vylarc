import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.app.routes import auth, system, credits, chat
from src.app.config import get_settings

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

# --- CORS / COOKIE SETTINGS ---
origins = [
    "https://vylarc.onrender.com",
    "https://vylarc.com",
    "https://platform.vylarc.com",
    "https://developer.vylarc.com",
    "http://localhost",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GLOBAL EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    try:
        from src.app.services.credit_service import CreditException
        if isinstance(exc, CreditException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
    except ImportError:
        pass
    
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
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
