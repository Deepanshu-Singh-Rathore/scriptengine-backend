"""
Database connection and schema setup.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import create_engine, Column, String, ARRAY, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from app.config import settings

Base = declarative_base()


class ApprovedScript(Base):
    """Approved script metadata table."""
    __tablename__ = "approved_scripts"
    __table_args__ = {'schema': settings.POSTGRES_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_type = Column(String, nullable=False, index=True)
    source_format = Column(String, nullable=True)
    target_format = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    intent = Column(ARRAY(String), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    repo_path = Column(String, nullable=False)
    config_path = Column(String, nullable=True)
    version = Column(String, nullable=True)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """User authentication table."""
    __tablename__ = "users"
    __table_args__ = {'schema': settings.POSTGRES_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())



from sqlalchemy.pool import NullPool

# Normalize postgres:// and postgresql:// to postgresql+psycopg2:// for SQLAlchemy compatibility
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(db_url, poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    try:
        print("Attempting to connect to database...")
        with engine.connect() as conn:
            # Create schema if custom schema specified and not default public
            if settings.POSTGRES_SCHEMA and settings.POSTGRES_SCHEMA != "public":
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.POSTGRES_SCHEMA}"))
                conn.commit()
            
            # Enable pgvector extension (supported natively by Neon and PostgreSQL)
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            except Exception as ext_err:
                print(f"Notice on CREATE EXTENSION: {ext_err}")
            
            # Set search_path to include schema and public for vector type
            conn.execute(text(f"SET search_path TO {settings.POSTGRES_SCHEMA}, public"))
            conn.commit()
        
        # Create tables in the specified schema
        Base.metadata.create_all(bind=engine)
        print("✓ Database initialized successfully!")
    except Exception as e:
        print("=" * 80)
        print("⚠️  WARNING: Database connection failed!")
        print(f"Error: {str(e)}")
        print("The application will start but database features will not work.")
        print("Please check your DATABASE_URL and network connectivity.")
        print("=" * 80)
        # Don't raise the exception - allow the app to start anyway



def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
