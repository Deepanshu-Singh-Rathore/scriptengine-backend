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
