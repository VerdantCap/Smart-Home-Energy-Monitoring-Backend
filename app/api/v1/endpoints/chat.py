from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.core.deps import (
    get_current_active_user, 
    get_current_admin_user,
    chat_rate_limiter,
    general_rate_limiter,
    AuthUser,
    get_current_user_token
)
from app.schemas.chat import (
    ChatRequest, 
    ChatResponse, 
    ConversationHistory,
    AIServiceHealth,
    ConversationSummary,
    QueryAnalytics
)
from app.services.ai_service import get_ai_service, AIService
from app.core.redis_client import conversation_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: Request,
    chat_request: ChatRequest,
    current_user: AuthUser = Depends(get_current_active_user),
    token: str = Depends(get_current_user_token),
    ai_service: AIService = Depends(get_ai_service),
    _: None = Depends(chat_rate_limiter)
):
    """Process a natural language query about energy data"""
    try:
        start_time = datetime.utcnow()
        
        # Process the chat request
        response = await ai_service.process_chat_request(chat_request, current_user, token)
        
        # Log analytics
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(
            f"Chat query processed successfully - user_id: {current_user.id}, "
            f"query_length: {len(chat_request.message)}, "
            f"processing_time_ms: {processing_time}, "
            f"confidence: {response.confidence}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat query"
        )


@router.get("/conversation", response_model=Optional[ConversationHistory])
async def get_conversation_history(
    current_user: AuthUser = Depends(get_current_active_user),
    ai_service: AIService = Depends(get_ai_service),
    _: None = Depends(general_rate_limiter)
):
    """Get conversation history for the current user"""
    try:
        history = await ai_service.get_conversation_history(current_user)
        
        if not history:
            return None
        
        # Convert to response format
        messages = []
        for msg in history.get("messages", []):
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": datetime.fromisoformat(msg["timestamp"]) if msg.get("timestamp") else None
            })
        
        return ConversationHistory(
            conversation_id=str(current_user.id),  # Use user ID as conversation ID
            messages=messages,
            created_at=datetime.fromisoformat(history["created_at"]) if history.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(history["updated_at"]) if history.get("updated_at") else datetime.utcnow(),
            user_id=current_user.id
        )
        
    except Exception as e:
        logger.error(f"Get conversation history error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation history"
        )


@router.delete("/conversation")
async def clear_conversation_history(
    current_user: AuthUser = Depends(get_current_active_user),
    ai_service: AIService = Depends(get_ai_service),
    _: None = Depends(general_rate_limiter)
):
    """Clear conversation history for the current user"""
    try:
        success = await ai_service.clear_conversation_history(current_user)
        
        if success:
            logger.info(f"Conversation history cleared for user {current_user.id}")
            return {"message": "Conversation history cleared successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear conversation history"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clear conversation history error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear conversation history"
        )


@router.get("/suggestions")
async def get_suggested_questions(
    current_user: AuthUser = Depends(get_current_active_user),
    _: None = Depends(general_rate_limiter)
):
    """Get suggested questions for the user"""
    try:
        # Return common suggested questions
        suggestions = [
            "How much energy did my fridge use today?",
            "What's my total energy consumption this week?",
            "Which device is using the most power right now?",
            "Show me my energy usage summary for yesterday",
            "How can I reduce my energy consumption?",
            "What's the current status of all my devices?",
            "Compare my energy usage this week vs last week",
            "Give me energy-saving recommendations"
        ]
        
        return {
            "suggestions": suggestions,
            "categories": {
                "device_specific": [
                    "How much energy did my fridge use today?",
                    "What's the current status of all my devices?"
                ],
                "summaries": [
                    "What's my total energy consumption this week?",
                    "Show me my energy usage summary for yesterday"
                ],
                "real_time": [
                    "Which device is using the most power right now?"
                ],
                "recommendations": [
                    "How can I reduce my energy consumption?",
                    "Give me energy-saving recommendations"
                ],
                "comparisons": [
                    "Compare my energy usage this week vs last week"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Get suggested questions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get suggested questions"
        )


@router.get("/health", response_model=AIServiceHealth)
async def get_ai_service_health(
    current_user: AuthUser = Depends(get_current_admin_user)
):
    """Get AI service health metrics (admin only)"""
    try:
        # Check OpenAI status
        from app.core.config import settings
        openai_status = "configured" if (settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here") else "not_configured"
        
        # Check Redis status
        try:
            await conversation_cache.get_client()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"
        
        return AIServiceHealth(
            service="ai-service",
            status="healthy" if all(s in ["healthy", "configured"] for s in [redis_status]) else "degraded",
            timestamp=datetime.utcnow(),
            openai_status=openai_status,
            redis_status=redis_status,
            telemetry_service_status="healthy",  # Internal service now
            auth_service_status="healthy",  # Internal service now
            active_conversations=0,  # Could be implemented with Redis tracking
            total_queries_today=0,  # Could be implemented with Redis counters
            average_response_time_ms=0.0  # Could be implemented with metrics collection
        )
        
    except Exception as e:
        logger.error(f"Get AI service health error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI service health"
        )


@router.post("/test")
async def test_ai_response(
    message: str,
    current_user: AuthUser = Depends(get_current_admin_user),
    token: str = Depends(get_current_user_token),
    ai_service: AIService = Depends(get_ai_service)
):
    """Test AI response generation (admin only)"""
    try:
        # Create a test chat request
        test_request = ChatRequest(
            message=message,
            include_context=False
        )
        
        # Process the request
        response = await ai_service.process_chat_request(test_request, current_user, token)
        
        return {
            "test_message": message,
            "ai_response": response.message,
            "confidence": response.confidence,
            "data_sources": response.data_sources,
            "suggested_questions": response.suggested_questions,
            "processing_timestamp": response.timestamp
        }
        
    except Exception as e:
        logger.error(f"Test AI response error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test AI response"
        )


@router.get("/analytics")
async def get_conversation_analytics(
    current_user: AuthUser = Depends(get_current_admin_user),
    _: None = Depends(general_rate_limiter)
):
    """Get conversation analytics (admin only)"""
    try:
        # This would typically pull from a database or analytics service
        # For now, return mock data
        return {
            "total_conversations": 0,
            "active_users": 0,
            "most_common_intents": [
                {"intent": "energy_summary", "count": 45, "percentage": 30.0},
                {"intent": "device_stats", "count": 38, "percentage": 25.3},
                {"intent": "realtime_metrics", "count": 32, "percentage": 21.3},
                {"intent": "recommendations", "count": 20, "percentage": 13.3},
                {"intent": "general", "count": 15, "percentage": 10.0}
            ],
            "average_response_time_ms": 850.0,
            "success_rate": 0.95,
            "user_satisfaction": 4.2,
            "peak_usage_hours": [9, 10, 11, 19, 20, 21],
            "daily_query_count": {
                "monday": 120,
                "tuesday": 135,
                "wednesday": 142,
                "thursday": 138,
                "friday": 155,
                "saturday": 98,
                "sunday": 87
            }
        }
        
    except Exception as e:
        logger.error(f"Get conversation analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation analytics"
        )


@router.get("/examples")
async def get_query_examples(
    current_user: AuthUser = Depends(get_current_active_user),
    _: None = Depends(general_rate_limiter)
):
    """Get example queries that users can try"""
    try:
        examples = {
            "device_queries": [
                "How much energy did my fridge use yesterday?",
                "What's the current power consumption of my AC?",
                "Show me the washing machine usage for this week",
                "Is my TV consuming more energy than usual?"
            ],
            "summary_queries": [
                "What's my total energy consumption today?",
                "Give me an energy summary for this month",
                "How much energy did I use last week?",
                "What's my average daily energy consumption?"
            ],
            "comparison_queries": [
                "Compare my energy usage this week vs last week",
                "Which device uses the most energy?",
                "How does today's consumption compare to yesterday?",
                "Show me the difference between weekday and weekend usage"
            ],
            "recommendation_queries": [
                "How can I reduce my energy consumption?",
                "What are some energy-saving tips for my home?",
                "Which devices should I focus on for energy savings?",
                "Give me personalized energy efficiency recommendations"
            ],
            "real_time_queries": [
                "What's my current energy usage?",
                "Which devices are active right now?",
                "Show me real-time power consumption",
                "What's the current status of all my devices?"
            ]
        }
        
        return {
            "examples": examples,
            "tips": [
                "Be specific about time periods (today, yesterday, this week, etc.)",
                "Mention specific devices by name (fridge, AC, washing machine, etc.)",
                "Ask for comparisons to understand trends",
                "Request recommendations for energy savings",
                "Use natural language - I understand conversational queries!"
            ]
        }
        
    except Exception as e:
        logger.error(f"Get query examples error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get query examples"
        )
