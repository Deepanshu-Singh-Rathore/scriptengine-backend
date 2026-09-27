"""
FastAPI main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import scripts, search, auth, templates
from app.database import init_db

app = FastAPI(
    title="Script Engine",
    description="Local, reuse-first script generator powered by Gemini",
    version="1.0.0"
)

import os

# CORS origins configuration
cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://scriptengine-frontend-production.up.railway.app",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:3000",
    "http://0.0.0.0:8000",
]

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    for url in frontend_url.split(","):
        url = url.strip()
        if url and url not in cors_origins:
            cors_origins.append(url)

# CORS middleware for local development and Vercel/Railway deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Conversion AI API"}


@app.get("/api/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "service": "conversion-ai",
        "version": "1.0.0"
    }
