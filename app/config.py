"""
Application configuration.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings."""
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/conversion_ai")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "conversion_ai")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_SCHEMA: str = os.getenv("POSTGRES_SCHEMA", "public")
    
    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # JWT Authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    
    # GitHub
    GITHUB_REPO_PATH: str = os.getenv("GITHUB_REPO_PATH", "./approved-scripts")
    GITHUB_REPO_URL: str = os.getenv("GITHUB_REPO_URL", "")
    
    # Search
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.8"))
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    
    # Script paths
    PENDING_PATH: str = os.path.join(GITHUB_REPO_PATH, "_pending")
    CONFIG_PATH: str = "/mnt/scratch/scripts/config.json"
    
    # Preview settings
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    PREVIEW_SAMPLE_SIZE: int = int(os.getenv("PREVIEW_SAMPLE_SIZE", "100"))
    PREVIEW_TIMEOUT_SECONDS: int = int(os.getenv("PREVIEW_TIMEOUT_SECONDS", "5"))


settings = Settings()

# Debug: Print environment variables
print("=" * 80)
print("ENVIRONMENT VARIABLES DEBUG")
print("=" * 80)
print(f"DATABASE_URL: {settings.DATABASE_URL[:50]}..." if len(settings.DATABASE_URL) > 50 else f"DATABASE_URL: {settings.DATABASE_URL}")
print(f"POSTGRES_HOST: {settings.POSTGRES_HOST}")
print(f"POSTGRES_PORT: {settings.POSTGRES_PORT}")
print(f"POSTGRES_DB: {settings.POSTGRES_DB}")
print(f"POSTGRES_USER: {settings.POSTGRES_USER}")
print(f"POSTGRES_PASSWORD: {'*' * len(settings.POSTGRES_PASSWORD) if settings.POSTGRES_PASSWORD else 'NOT SET'}")
print(f"POSTGRES_SCHEMA: {settings.POSTGRES_SCHEMA}")
print(f"GEMINI_API_KEY: {'SET' if settings.GEMINI_API_KEY else 'NOT SET'}")
print(f"JWT_SECRET_KEY: {'SET' if settings.JWT_SECRET_KEY else 'NOT SET'}")
print(f"GITHUB_REPO_PATH: {settings.GITHUB_REPO_PATH}")
print("=" * 80)
