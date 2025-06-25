from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer
import uvicorn
import logging
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.core.redis_client import init_redis
from app.api.v1.api import api_router
from app.core.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting up Smart Home Unified Service...")
    await init_db()
    await init_redis()
    logger.info("Smart Home Unified Service startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Smart Home Unified Service...")


# Create FastAPI app
app = FastAPI(
    title="Smart Home Unified Service",
    description="Unified service combining Authentication, AI, and Telemetry for Smart Home Energy Monitoring",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Health check endpoints for backward compatibility
@app.get("/api/auth/health")
async def auth_health_check():
    """Auth service health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-service",
        "module": "auth",
        "version": "1.0.0"
    }

@app.get("/api/chat/health")
async def ai_health_check():
    """AI service health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-service",
        "module": "ai",
        "version": "1.0.0",
        "openai_configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here")
    }

@app.get("/api/telemetry/health")
async def telemetry_health_check():
    """Telemetry service health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-service",
        "module": "telemetry",
        "version": "1.0.0"
    }

# Main health check endpoint
@app.get("/api/health")
async def health_check():
    """Main health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-service",
        "version": "1.0.0",
        "modules": ["auth", "ai", "telemetry"],
        "openai_configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here")
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Smart Home Unified Service",
        "description": "Combined Authentication, AI, and Telemetry Service",
        "version": "1.0.0",
        "docs": "/docs",
        "modules": ["auth", "ai", "telemetry"]
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
