from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, telemetry

api_router = APIRouter()

# Include auth endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# Include chat/AI endpoints
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

# Include telemetry endpoints
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
