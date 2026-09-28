import os
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routers import scripts, search, auth, templates
from app.database import init_db

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Script Engine",
    description="Local, reuse-first script generator powered by Gemini",
    version="1.0.0"
)

class ExceptionCORSFixMiddleware(BaseHTTPMiddleware):
    """
    Middleware that catches all unhandled exceptions and returns a JSON 500 response.
    Because this middleware is registered before CORSMiddleware, the response generated here
    flows through CORSMiddleware, ensuring CORS headers (Access-Control-Allow-Origin, etc.)
    are ALWAYS attached even on 500 Internal Server Errors.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled exception on {request.method} {request.url}: {traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": str(exc) or "Internal server error occurred",
                    "error_type": type(exc).__name__
                }
            )

# CORS origins configuration
cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://scriptengine-frontend.vercel.app",
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

# Register ExceptionCORSFixMiddleware first so CORSMiddleware wraps it (executes outside it)
app.add_middleware(ExceptionCORSFixMiddleware)

# CORS middleware for local development and Vercel/Render deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r".*",
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
