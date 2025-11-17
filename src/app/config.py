import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loads and validates all environment variables for the application.
    """
    # model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

    # Core
    DATABASE_URL: str
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    
    # Security
    ENCRYPTION_KEY: str  # 32-byte (256-bit) AES key, hex-encoded
    FLASK_SECRET_KEY: str # Used as JWT_SECRET_KEY for signing tokens

    # API Keys
    GEMINI_API_KEY: str
    OPENAI_API_KEY: str
    GOOGLE_MAPS_API_KEY: str

# Secret for validating WooCommerce webhook
    WORDPRESS_SECRET_KEY: str

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