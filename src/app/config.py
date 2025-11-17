import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loads and validates all environment variables for the application.
    """
    # Core
    DATABASE_URL: str
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    
    # Security
    ENCRYPTION_KEY: str
    FLASK_SECRET_KEY: str 
    WORDPRESS_SECRET_KEY: str

    # API Keys
    GEMINI_API_KEY: str
    OPENAI_API_KEY: str
    GOOGLE_MAPS_API_KEY: str
    
    # --- THIS IS THE FIX ---
    # Admin Backdoor Email
    ADMIN_EMAIL: str = "noreply@vylarc.com" # Default value if not set
    # --- END FIX ---

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "/auth/google/callback"

    # JWT Settings
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    @property
    def FULL_GOOGLE_REDIRECT_URI(self) -> str:
        """Constructs the full callback URL for Google OAuth."""
        return f"{self.PUBLIC_BASE_URL.rstrip('/')}{self.GOOGLE_REDIRECT_URI}"

@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the Settings object.
    Loads from .env file if present (for local dev).
    """
    # Check if .env file exists and load it
    if os.path.exists(".env"):
        return Settings(_env_file=".env", _env_file_encoding='utf-8')
    return Settings()