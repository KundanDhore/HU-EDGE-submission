"""
Main FastAPI application entry point.
"""
import time

from fastapi import FastAPI
from fastapi import Request

from .core.logging import get_logger
from .db.session import engine
from .db.init_db import init_db
from .models.base import Base
from .api.v1 import auth, users, projects, search, chat, analysis_configs, documentation, admin

# Initialize logger
logger = get_logger(__name__)

logger.info("Starting application initialization...")

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified successfully")
except Exception as e:
    logger.error(f"Failed to create database tables: {e}", exc_info=True)
    raise

# Initialize FastAPI app
app = FastAPI(
    title="HU Edge Backend API",
    version="1.0.0",
    description="Intelligent Code Analysis and Chat Platform"
)
logger.info("FastAPI application initialized successfully")

# Log every request at INFO so "important" runtime activity is visible in terminal.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Request failed | %s %s | elapsed_ms=%.1f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Request | %s %s | status=%s | elapsed_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

# Register routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(search.router, tags=["Search"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(analysis_configs.router, tags=["Analysis Configs"])
app.include_router(documentation.router, tags=["Documentation"])
app.include_router(admin.router, tags=["Admin"])


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "HU Edge Backend API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
