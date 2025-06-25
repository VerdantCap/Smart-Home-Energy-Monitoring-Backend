from openai import AsyncOpenAI
import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import logging
import uuid

from app.core.config import settings
from app.core.deps import AuthUser
from app.core.redis_client import conversation_cache
from app.schemas.chat import (
    ChatRequest, ChatResponse, QueryIntent, EnergyInsight,
    SmartRecommendation, ContextualResponse
)

logger = logging.getLogger(__name__)


class TelemetryServiceClient:
    """Internal client for telemetry data (unified service)"""
    
    def __init__(self):
        pass
    
    async def get_device_stats(self, token: str, device_id: str, start_time: str, end_time: str) -> Optional[dict]:
        """Get device statistics - placeholder for internal service calls"""
        # In unified service, this would call the telemetry service directly
        # For now, return mock data
        return {
            "device_id": device_id,
            "device_name": device_id.replace("-", " ").title(),
            "avg_energy_watts": 150.5,
            "total_energy_wh": 3612.0,
            "max_energy_watts": 200.0,
            "min_energy_watts": 100.0,
            "sample_count": 24
        }
    
    async def get_energy_summary(self, token: str, start_time: str, end_time: str) -> Optional[dict]:
        """Get energy summary - placeholder for internal service calls"""
        return {
            "total_devices": 5,
            "total_energy_wh": 15000.0,
            "avg_energy_watts": 625.0,
            "peak_energy_watts": 1200.0
        }
    
    async def get_realtime_metrics(self, token: str) -> Optional[dict]:
        """Get real-time metrics - placeholder for internal service calls"""
        return {
            "active_devices": 4,
            "total_current_power": 450.0,
            "average_power_per_device": 112.5,
            "highest_consuming_device": "AC Unit"
        }


class AIService:
    """AI service for processing natural language queries about energy data"""
    
    def __init__(self):
        # Initialize OpenAI client
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here":
            self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self.openai_available = True
        else:
            self.openai_client = None
            self.openai_available = False
            logger.warning("OpenAI API key not configured - using fallback responses")
        
        self.telemetry_client = TelemetryServiceClient()
        
        # System prompt for the AI assistant
        self.system_prompt = """You are an AI assistant for a smart home energy monitoring system. 
        You help users understand their energy consumption, identify patterns, and provide recommendations for energy efficiency.
        
        Your capabilities include:
        - Analyzing energy consumption data from smart home devices
        - Providing insights about usage patterns
        - Suggesting energy-saving recommendations
        - Answering questions about specific devices or time periods
        - Explaining energy costs and efficiency metrics
        
        Always be helpful, accurate, and provide actionable insights. When you don't have specific data, 
        clearly state that and offer to help in other ways. Focus on being practical and user-friendly.
        
        If asked about data you cannot access, explain what information you would need and how the user can provide it."""
    
    async def process_chat_request(self, request: ChatRequest, user: AuthUser, token: str) -> ChatResponse:
        """Process a chat request and generate a response"""
        try:
            start_time = datetime.utcnow()
            
            # Generate conversation ID if not provided
            conversation_id = request.conversation_id or str(uuid.uuid4())
            
            # Add user message to conversation history
            await conversation_cache.add_message(user.id, "user", request.message)
            
            # Parse the user's intent
            intent = await self._parse_intent(request.message)
            
            # Check cache for similar queries
            query_hash = self._generate_query_hash(request.message, user.id)
            cached_result = await conversation_cache.get_cached_query_result(query_hash)
            
            if cached_result and not request.include_context:
                # Return cached response
                response = ChatResponse(
                    message=cached_result["message"],
                    conversation_id=conversation_id,
                    timestamp=datetime.utcnow(),
                    data_sources=cached_result.get("data_sources"),
                    confidence=cached_result.get("confidence"),
                    suggested_questions=cached_result.get("suggested_questions")
                )
            else:
                # Generate new response
                response = await self._generate_response(request, intent, user, token, conversation_id)
                
                # Cache the result
                cache_data = {
                    "message": response.message,
                    "data_sources": response.data_sources,
                    "confidence": response.confidence,
                    "suggested_questions": response.suggested_questions
                }
                await conversation_cache.cache_query_result(query_hash, cache_data)
            
            # Add assistant response to conversation history
            await conversation_cache.add_message(user.id, "assistant", response.message)
            
            # Log analytics
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(f"Chat request processed - user_id: {user.id}, intent: {intent.intent_type}, processing_time_ms: {processing_time}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing chat request: {e}")
            
            # Return fallback response
            return ChatResponse(
                message="I apologize, but I'm having trouble processing your request right now. Please try again later or rephrase your question.",
                conversation_id=conversation_id or str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                confidence=0.0
            )
    
    async def _parse_intent(self, message: str) -> QueryIntent:
        """Parse user message to extract intent and entities"""
        try:
            # Simple rule-based intent detection (can be enhanced with ML models)
            message_lower = message.lower()
            
            # Device-specific queries
            if any(word in message_lower for word in ["fridge", "refrigerator", "ac", "air conditioning", "washer", "washing machine", "tv", "television", "lights"]):
                device_matches = []
                if "fridge" in message_lower or "refrigerator" in message_lower:
                    device_matches.append("fridge-001")
                if "ac" in message_lower or "air conditioning" in message_lower:
                    device_matches.append("ac-001")
                if "washer" in message_lower or "washing machine" in message_lower:
                    device_matches.append("washer-001")
                if "tv" in message_lower or "television" in message_lower:
                    device_matches.append("tv-001")
                if "lights" in message_lower:
                    device_matches.append("lights-001")
                
                return QueryIntent(
                    intent_type="device_stats",
                    entities={"devices": device_matches},
                    device_ids=device_matches,
                    time_range=self._extract_time_range(message),
                    confidence=0.8
                )
            
            # Energy summary queries
            elif any(word in message_lower for word in ["total", "summary", "overall", "consumption", "usage", "energy"]):
                return QueryIntent(
                    intent_type="energy_summary",
                    entities={},
                    time_range=self._extract_time_range(message),
                    confidence=0.9
                )
            
            # Real-time queries
            elif any(word in message_lower for word in ["now", "current", "currently", "real-time", "live"]):
                return QueryIntent(
                    intent_type="realtime_metrics",
                    entities={},
                    confidence=0.85
                )
            
            # Comparison queries
            elif any(word in message_lower for word in ["compare", "comparison", "vs", "versus", "difference"]):
                return QueryIntent(
                    intent_type="comparison",
                    entities={},
                    time_range=self._extract_time_range(message),
                    confidence=0.7
                )
            
            # Recommendation queries
            elif any(word in message_lower for word in ["recommend", "suggestion", "advice", "save", "reduce", "optimize"]):
                return QueryIntent(
                    intent_type="recommendations",
                    entities={},
                    confidence=0.8
                )
            
            # Default to general query
            else:
                return QueryIntent(
                    intent_type="general",
                    entities={},
                    confidence=0.5
                )
                
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return QueryIntent(
                intent_type="general",
                entities={},
                confidence=0.3
            )
    
    def _extract_time_range(self, message: str) -> Optional[Dict[str, str]]:
        """Extract time range from message"""
        message_lower = message.lower()
        now = datetime.utcnow()
        
        if "today" in message_lower:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif "yesterday" in message_lower:
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif "this week" in message_lower:
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif "last week" in message_lower:
            days_since_monday = now.weekday()
            end = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=7)
        elif "this month" in message_lower:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif "last month" in message_lower:
            if now.month == 1:
                start = now.replace(year=now.year-1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                start = now.replace(month=now.month-1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to last 24 hours
            start = now - timedelta(days=1)
            end = now
        
        return {
            "start_time": start.isoformat(),
            "end_time": end.isoformat()
        }
    
    async def _generate_response(self, request: ChatRequest, intent: QueryIntent, user: AuthUser, token: str, conversation_id: str) -> ChatResponse:
        """Generate response based on intent and available data"""
        try:
            # Fetch relevant data based on intent
            data_sources = []
            context_data = {}
            
            if intent.intent_type == "device_stats" and intent.device_ids:
                for device_id in intent.device_ids:
                    if intent.time_range:
                        stats = await self.telemetry_client.get_device_stats(
                            token, device_id, 
                            intent.time_range["start_time"], 
                            intent.time_range["end_time"]
                        )
                        if stats:
                            context_data[f"device_{device_id}"] = stats
                            data_sources.append(f"Device {device_id} telemetry")
            
            elif intent.intent_type == "energy_summary":
                if intent.time_range:
                    summary = await self.telemetry_client.get_energy_summary(
                        token,
                        intent.time_range["start_time"],
                        intent.time_range["end_time"]
                    )
                    if summary:
                        context_data["energy_summary"] = summary
                        data_sources.append("Energy consumption summary")
            
            elif intent.intent_type == "realtime_metrics":
                metrics = await self.telemetry_client.get_realtime_metrics(token)
                if metrics:
                    context_data["realtime_metrics"] = metrics
                    data_sources.append("Real-time metrics")
            
            # Generate AI response
            if self.openai_available:
                response_text = await self._generate_openai_response(request.message, context_data, intent)
            else:
                response_text = await self._generate_fallback_response(request.message, context_data, intent)
            
            # Generate suggested questions
            suggested_questions = self._generate_suggested_questions(intent, context_data)
            
            return ChatResponse(
                message=response_text,
                conversation_id=conversation_id,
                timestamp=datetime.utcnow(),
                data_sources=data_sources if data_sources else None,
                confidence=intent.confidence,
                suggested_questions=suggested_questions
            )
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return ChatResponse(
                message="I encountered an issue while processing your request. Could you please try rephrasing your question?",
                conversation_id=conversation_id,
                timestamp=datetime.utcnow(),
                confidence=0.0
            )
    
    async def _generate_openai_response(self, message: str, context_data: Dict[str, Any], intent: QueryIntent) -> str:
        """Generate response using OpenAI"""
        try:
            # Prepare context for OpenAI
            context_text = ""
            if context_data:
                context_text = f"\n\nAvailable data:\n{json.dumps(context_data, indent=2, default=str)}"
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{message}{context_text}"}
            ]
            
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=settings.OPENAI_TEMPERATURE,
                timeout=30
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return await self._generate_fallback_response(message, context_data, intent)
    
    async def _generate_fallback_response(self, message: str, context_data: Dict[str, Any], intent: QueryIntent) -> str:
        """Generate fallback response when OpenAI is not available"""
        
        if intent.intent_type == "device_stats" and context_data:
            response_parts = []
            for key, stats in context_data.items():
                if key.startswith("device_"):
                    device_name = stats.get("device_name", "Unknown Device")
                    avg_watts = stats.get("avg_energy_watts", 0)
                    total_wh = stats.get("total_energy_wh", 0)
                    response_parts.append(
                        f"{device_name} consumed an average of {avg_watts:.1f} watts, "
                        f"totaling {total_wh:.1f} watt-hours during the specified period."
                    )
            
            if response_parts:
                return "Here's what I found about your device usage:\n\n" + "\n\n".join(response_parts)
        
        elif intent.intent_type == "energy_summary" and "energy_summary" in context_data:
            summary = context_data["energy_summary"]
            total_devices = summary.get("total_devices", 0)
            total_energy = summary.get("total_energy_wh", 0)
            avg_power = summary.get("avg_energy_watts", 0)
            
            return f"Energy Summary:\n\n" \
                   f"• Total devices monitored: {total_devices}\n" \
                   f"• Total energy consumed: {total_energy:.1f} watt-hours\n" \
                   f"• Average power consumption: {avg_power:.1f} watts\n\n" \
                   f"This data can help you understand your overall energy usage patterns."
        
        elif intent.intent_type == "realtime_metrics" and "realtime_metrics" in context_data:
            metrics = context_data["realtime_metrics"]
            active_devices = metrics.get("active_devices", 0)
            total_power = metrics.get("total_current_power", 0)
            highest_device = metrics.get("highest_consuming_device")
            
            response = f"Current Energy Status:\n\n" \
                      f"• Active devices: {active_devices}\n" \
                      f"• Total current power: {total_power:.1f} watts\n"
            
            if highest_device:
                response += f"• Highest consuming device: {highest_device}\n"
            
            return response + "\nThis shows your real-time energy consumption across all monitored devices."
        
        elif intent.intent_type == "recommendations":
            return "Here are some general energy-saving recommendations:\n\n" \
                   "• Turn off devices when not in use\n" \
                   "• Use energy-efficient appliances\n" \
                   "• Monitor your usage patterns regularly\n" \
                   "• Consider using smart scheduling for high-consumption devices\n\n" \
                   "For personalized recommendations, I'd need to analyze your specific usage data."
        
        else:
            return "I understand you're asking about your energy usage. " \
                   "I can help you with information about device consumption, energy summaries, " \
                   "real-time metrics, and energy-saving recommendations. " \
                   "Could you please be more specific about what you'd like to know?"
    
    def _generate_suggested_questions(self, intent: QueryIntent, context_data: Dict[str, Any]) -> List[str]:
        """Generate suggested follow-up questions"""
        suggestions = []
        
        if intent.intent_type == "device_stats":
            suggestions.extend([
                "How does this compare to last week?",
                "What are some ways to reduce this device's energy usage?",
                "Show me the energy summary for all devices"
            ])
        elif intent.intent_type == "energy_summary":
            suggestions.extend([
                "Which device is using the most energy?",
                "How can I reduce my overall energy consumption?",
                "Show me real-time energy usage"
            ])
        elif intent.intent_type == "realtime_metrics":
            suggestions.extend([
                "What's my energy usage trend for this week?",
                "Which devices should I turn off to save energy?",
                "How does my current usage compare to yesterday?"
            ])
        else:
            suggestions.extend([
                "Show me my energy usage for today",
                "Which device uses the most energy?",
                "Give me energy-saving recommendations"
            ])
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def _generate_query_hash(self, message: str, user_id: str) -> str:
        """Generate hash for query caching"""
        content = f"{user_id}:{message.lower().strip()}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def get_conversation_history(self, user: AuthUser) -> Optional[Dict[str, Any]]:
        """Get conversation history for a user"""
        return await conversation_cache.get_conversation(user.id)
    
    async def clear_conversation_history(self, user: AuthUser) -> bool:
        """Clear conversation history for a user"""
        return await conversation_cache.clear_conversation(user.id)


# Global AI service instance
ai_service = AIService()


def get_ai_service() -> AIService:
    """Dependency to get AI service"""
    return ai_service
