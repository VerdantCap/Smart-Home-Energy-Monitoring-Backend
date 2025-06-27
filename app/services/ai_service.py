from openai import AsyncOpenAI
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from app.core.config import settings
from app.core.deps import AuthUser
from app.core.redis_client import conversation_cache, redis_service
from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)




class TelemetryServiceClient:
    """telemetry service client with connection pooling and caching"""
    
    def __init__(self):
        self._connection_pool = None
        self._cache_ttl = 60  # 1 minute cache for telemetry data
    
    async def get_device_stats(self, user: AuthUser, device_id: str, start_time: str, end_time: str) -> Optional[dict]:
        """Get device statistics using actual telemetry service"""
        try:
            # Check cache first
            cache_key = f"device_stats:{user.id}:{device_id}:{start_time}:{end_time}"
            cached_result = await redis_service.get(cache_key)
            
            if cached_result:
                return json.loads(cached_result)
            
            # Get from database
            async for db in get_db():
                telemetry_service = TelemetryService(db)
                
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                
                stats = await telemetry_service.get_telemetry_stats(device_id, start_dt, end_dt, user)
                
                if stats:
                    result = {
                        "device_id": stats.device_id,
                        "device_name": stats.device_name or device_id.replace("-", " ").title(),
                        "avg_energy_watts": stats.avg_energy_watts,
                        "total_energy_wh": stats.total_energy_wh,
                        "max_energy_watts": stats.max_energy_watts,
                        "min_energy_watts": stats.min_energy_watts,
                        "sample_count": stats.sample_count
                    }
                    
                    # Cache the result
                    await redis_service.set(cache_key, json.dumps(result), expire=self._cache_ttl)
                    return result
                
                break
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting device stats: {e}")
            return None
    
    async def get_energy_summary(self, user: AuthUser, start_time: str, end_time: str) -> Optional[dict]:
        """Get energy summary using actual telemetry service"""
        try:
            # Check cache first
            cache_key = f"energy_summary:{user.id}:{start_time}:{end_time}"
            cached_result = await redis_service.get(cache_key)
            
            if cached_result:
                return json.loads(cached_result)
            
            # Get from database
            async for db in get_db():
                telemetry_service = TelemetryService(db)
                
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                
                summary = await telemetry_service.get_energy_consumption_summary(start_dt, end_dt, user)
                
                if summary:
                    result = {
                        "total_devices": summary.total_devices,
                        "total_energy_wh": summary.total_energy_wh,
                        "avg_energy_watts": summary.avg_energy_watts,
                        "peak_energy_watts": summary.peak_energy_watts
                    }
                    
                    # Cache the result
                    await redis_service.set(cache_key, json.dumps(result), expire=self._cache_ttl)
                    return result
                
                break
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting energy summary: {e}")
            return None
    
    async def get_realtime_metrics(self, user: AuthUser) -> Optional[dict]:
        """Get real-time metrics using actual telemetry service"""
        try:
            # Check cache first (shorter TTL for real-time data)
            cache_key = f"realtime_metrics:{user.id}"
            cached_result = await redis_service.get(cache_key)
            
            if cached_result:
                return json.loads(cached_result)
            
            # Get from database
            async for db in get_db():
                telemetry_service = TelemetryService(db)
                
                metrics = await telemetry_service.get_real_time_metrics(user)
                
                if metrics:
                    result = {
                        "active_devices": metrics.active_devices,
                        "total_current_power": metrics.total_current_power,
                        "average_power_per_device": metrics.average_power_per_device,
                        "highest_consuming_device": metrics.highest_consuming_device
                    }
                    
                    # Cache for 30 seconds (real-time data)
                    await redis_service.set(cache_key, json.dumps(result), expire=30)
                    return result
                
                break
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting real-time metrics: {e}")
            return None


class AIService:
    """AI service that always fetches comprehensive data and sends it to OpenAI for intelligent analysis"""
    
    def __init__(self):
        # Initialize OpenAI client with connection pooling
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here":
            self.openai_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                max_retries=2
            )
            self.openai_available = True
        else:
            self.openai_client = None
            self.openai_available = False
            logger.warning("OpenAI API key not configured - using fallback responses")
        
        # Initialize telemetry client for data fetching
        self.telemetry_client = TelemetryServiceClient()
        
        # Thread pool for CPU-intensive tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        # Performance metrics
        self.request_count = 0
        self.total_processing_time = 0.0
        
        # SQL generation prompt for query analysis
        self.sql_generation_prompt = """You are an expert SQL query generator for a smart home energy monitoring system. Your task is to analyze user queries and generate appropriate SQL queries to fetch the required data.

        Database Schema:
        
        1. **telemetry** table:
           - id (UUID, primary key)
           - device_id (VARCHAR, indexed) - Device identifier (e.g., 'fridge-001', 'ac-001', 'tv-001', 'lights-001', 'washer-001')
           - user_id (UUID, indexed) - User identifier
           - timestamp (TIMESTAMP, indexed) - When the measurement was taken
           - energy_watts (NUMERIC) - Power consumption in watts
           - created_at (TIMESTAMP) - Record creation time

        2. **devices** table:
           - id (UUID, primary key)
           - user_id (UUID, indexed) - User identifier
           - device_id (VARCHAR, indexed) - Device identifier
           - name (VARCHAR) - Human-readable device name
           - type (VARCHAR) - Device type (e.g., 'appliance', 'lighting', 'hvac')
           - location (VARCHAR) - Device location
           - is_active (BOOLEAN) - Whether device is active
           - created_at (TIMESTAMP)
           - updated_at (TIMESTAMP)

        Available Functions:
        - Use PostgreSQL syntax
        - Current timestamp: NOW()
        - Date functions: DATE_TRUNC(), EXTRACT(), AGE()
        - Aggregations: AVG(), SUM(), MAX(), MIN(), COUNT()
        - Window functions available

        Instructions:
        1. Analyze the user query to understand what data they need
        2. Generate efficient SQL queries that fetch only the required data
        3. Always include user_id filter for security: WHERE user_id = %s
        4. Use appropriate time ranges based on the query context
        5. Include JOINs with devices table when device names/info are needed
        6. Return multiple queries if different types of data are needed
        7. Optimize for performance with proper indexing

        Response Format:
        Return a JSON object with this structure:
        {
            "queries": [
                {
                    "purpose": "Description of what this query fetches",
                    "sql": "SELECT ... FROM ... WHERE ...",
                    "parameters": ["param1", "param2"]
                }
            ],
            "explanation": "Brief explanation of the data being fetched"
        }

        Example user queries and responses:
        - "Show my energy usage today" → Query for today's telemetry data
        - "Which device uses most energy?" → Query for device consumption ranking
        - "Compare this week vs last week" → Queries for both time periods
        - "Real-time status" → Query for latest readings per device
        """

        # Data analysis prompt for generating final responses
        self.data_analysis_prompt = """You are an advanced AI assistant for a smart home energy monitoring system. You have been provided with specific energy data fetched from the database based on the user's query.

        Your capabilities include:
        - Analyzing energy consumption patterns and trends
        - Identifying optimization opportunities and anomalies
        - Providing personalized, data-driven recommendations
        - Calculating cost implications and potential savings
        - Comparing device efficiency and usage patterns
        - Detecting unusual consumption patterns

        Response guidelines:
        - Analyze the provided data thoroughly and provide specific insights
        - Use concrete numbers and metrics from the actual data
        - Highlight significant patterns, trends, or anomalies
        - Offer practical, actionable recommendations
        - Calculate potential savings when relevant
        - Structure responses clearly with bullet points and sections
        - Be conversational but informative
        - If data shows concerning patterns, explain why and suggest solutions
        - Include relevant comparisons when multiple data points are available

        Focus on delivering maximum value by leveraging the specific data provided to give intelligent, personalized energy management insights."""
        
        # System prompt for comprehensive data analysis
        self.system_prompt = """You are an expert AI assistant for a smart home energy monitoring system. You help users understand their energy consumption patterns, optimize their usage, and reduce costs.

        Your expertise includes:
        - Energy consumption analysis and pattern recognition
        - Device efficiency optimization recommendations
        - Cost calculation and savings identification
        - Anomaly detection in energy usage
        - Personalized energy management strategies

        Always provide:
        - Data-driven insights using actual metrics
        - Specific, actionable recommendations
        - Clear explanations of energy patterns
        - Cost implications when relevant
        - Practical optimization suggestions

        Keep responses informative yet conversational, focusing on helping users make informed decisions about their energy usage."""
    
    async def process_chat_request(self, request: ChatRequest, user: AuthUser, token: str) -> ChatResponse:
        """Process a chat request using intelligent SQL generation workflow"""
        try:
            start_time = datetime.utcnow()
            
            # Generate conversation ID if not provided
            conversation_id = request.conversation_id or str(uuid.uuid4())
            
            # Add user message to conversation history
            await conversation_cache.add_message(user.id, "user", request.message)
            
            # Check cache for similar queries (optional optimization)
            query_hash = self._generate_query_hash(request.message, user.id)
            cached_result = await conversation_cache.get_cached_query_result(query_hash)
            
            if cached_result and not request.include_context:
                # Return cached response
                response = ChatResponse(
                    message=cached_result["message"],
                    conversation_id=conversation_id,
                    timestamp=datetime.utcnow(),
                    data_sources=cached_result.get("data_sources"),
                    confidence=cached_result.get("confidence", 0.9),
                    suggested_questions=cached_result.get("suggested_questions")
                )
            else:
                # New intelligent workflow: SQL generation → Data fetching → Analysis
                response = await self._generate_intelligent_response(request, user, token, conversation_id)
                
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
            logger.info(f"Chat request processed - user_id: {user.id}, processing_time_ms: {processing_time}")
            
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
    
    async def _generate_intelligent_response(self, request: ChatRequest, user: AuthUser, token: str, conversation_id: str) -> ChatResponse:
        """Generate response using intelligent SQL generation workflow"""
        try:
            # Step 1: Generate SQL queries based on user query
            sql_queries = await self._generate_sql_queries(request.message, user)
            
            # Step 2: Execute SQL queries to fetch targeted data
            fetched_data = await self._execute_sql_queries(sql_queries, user)
            
            # Step 3: Send data to OpenAI for analysis and response generation
            if self.openai_available:
                response_text = await self._generate_data_analysis_response(request.message, fetched_data)
            else:
                response_text = await self._generate_fallback_analysis_response(request.message, fetched_data)
            # Step 4: Generate contextual suggestions based on the data
            suggested_questions = self._generate_intelligent_suggestions(fetched_data, request.message)
            
            return ChatResponse(
                message=response_text,
                conversation_id=conversation_id,
                timestamp=datetime.utcnow(),
                data_sources=fetched_data.get("data_sources", []),
                confidence=0.95,  # High confidence with targeted data
                suggested_questions=suggested_questions
            )
            
        except Exception as e:
            logger.error(f"Error in intelligent response generation: {e}")
            # Fallback to comprehensive data approach
            return await self._generate_comprehensive_response(request, user, token, conversation_id)

    async def _generate_sql_queries(self, user_message: str, user: AuthUser) -> Dict[str, Any]:
        """Generate SQL queries based on user message using OpenAI"""
        try:
            if not self.openai_available:
                # Fallback to predefined queries for common patterns
                return self._generate_fallback_queries(user_message)
            
            messages = [
                {"role": "system", "content": self.sql_generation_prompt},
                {"role": "user", "content": f"User query: {user_message}"}
            ]
            
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.1,  # Low temperature for precise SQL generation
                max_tokens=1000,  # Limit tokens for SQL generation
                timeout=15  # Reduced timeout for SQL generation
            )
            
            # Parse the JSON response with better error handling
            response_content = response.choices[0].message.content.strip()
            
            # Clean up the response content to handle potential formatting issues
            if response_content.startswith('```json'):
                response_content = response_content[7:]
            if response_content.endswith('```'):
                response_content = response_content[:-3]
            
            # Clean up line continuation characters and extra whitespace
            response_content = response_content.replace('\\\n', ' ').replace('\\', '')
            response_content = ' '.join(response_content.split())  # Normalize whitespace
            
            try:
                sql_response = json.loads(response_content)
                logger.info(f"OpenAI generated SQL queries for user {user.id}: {len(sql_response.get('queries', []))} queries")
                return sql_response
            except json.JSONDecodeError as json_error:
                logger.error(f"JSON parsing error: {json_error}. Response content: {response_content}")
                # Fallback to predefined queries
                return self._generate_fallback_queries(user_message)
            
        except Exception as e:
            logger.error(f"Error generating SQL queries: {e}")
            # Fallback to predefined queries
            return self._generate_fallback_queries(user_message)

    def _generate_fallback_queries(self, user_message: str) -> Dict[str, Any]:
        """Generate fallback SQL queries for common patterns when OpenAI is unavailable"""
        message_lower = user_message.lower()
        queries = []
        
        # Real-time/current status queries
        if any(word in message_lower for word in ["current", "now", "real-time", "status"]):
            queries.append({
                "purpose": "Get latest readings per device for real-time status",
                "sql": """
                    SELECT DISTINCT ON (t.device_id) 
                           t.device_id, 
                           d.name as device_name,
                           t.energy_watts,
                           t.timestamp
                    FROM telemetry t
                    LEFT JOIN devices d ON t.device_id = d.device_id AND t.user_id = d.user_id
                    WHERE t.user_id = %s 
                      AND t.timestamp >= NOW() - INTERVAL '5 minutes'
                    ORDER BY t.device_id, t.timestamp DESC
                """,
                "parameters": ["user_id"]
            })
        
        # Today's usage
        elif any(word in message_lower for word in ["today", "daily"]):
            queries.append({
                "purpose": "Get today's energy consumption by device",
                "sql": """
                    SELECT t.device_id,
                           d.name as device_name,
                           AVG(t.energy_watts) as avg_watts,
                           SUM(t.energy_watts) as total_energy_wh,
                           COUNT(*) as sample_count
                    FROM telemetry t
                    LEFT JOIN devices d ON t.device_id = d.device_id AND t.user_id = d.user_id
                    WHERE t.user_id = %s 
                      AND t.timestamp >= DATE_TRUNC('day', NOW())
                    GROUP BY t.device_id, d.name
                    ORDER BY total_energy_wh DESC
                """,
                "parameters": ["user_id"]
            })
        
        # Device comparison or ranking
        elif any(word in message_lower for word in ["which device", "most energy", "highest", "compare"]):
            queries.append({
                "purpose": "Rank devices by energy consumption (last 24 hours)",
                "sql": """
                    SELECT t.device_id,
                           d.name as device_name,
                           AVG(t.energy_watts) as avg_watts,
                           SUM(t.energy_watts) as total_energy_wh,
                           MAX(t.energy_watts) as peak_watts
                    FROM telemetry t
                    LEFT JOIN devices d ON t.device_id = d.device_id AND t.user_id = d.user_id
                    WHERE t.user_id = %s 
                      AND t.timestamp >= NOW() - INTERVAL '24 hours'
                    GROUP BY t.device_id, d.name
                    ORDER BY total_energy_wh DESC
                """,
                "parameters": ["user_id"]
            })
        
        # Weekly trends
        elif any(word in message_lower for word in ["week", "trend", "pattern"]):
            queries.append({
                "purpose": "Get weekly energy consumption trends",
                "sql": """
                    SELECT DATE_TRUNC('day', t.timestamp) as day,
                           SUM(t.energy_watts) as daily_energy_wh,
                           AVG(t.energy_watts) as avg_watts
                    FROM telemetry t
                    WHERE t.user_id = %s 
                      AND t.timestamp >= NOW() - INTERVAL '7 days'
                    GROUP BY DATE_TRUNC('day', t.timestamp)
                    ORDER BY day
                """,
                "parameters": ["user_id"]
            })
        
        # Default: general overview
        else:
            queries.extend([
                {
                    "purpose": "Get recent energy overview",
                    "sql": """
                        SELECT t.device_id,
                               d.name as device_name,
                               AVG(t.energy_watts) as avg_watts,
                               SUM(t.energy_watts) as total_energy_wh
                        FROM telemetry t
                        LEFT JOIN devices d ON t.device_id = d.device_id AND t.user_id = d.user_id
                        WHERE t.user_id = %s 
                          AND t.timestamp >= NOW() - INTERVAL '24 hours'
                        GROUP BY t.device_id, d.name
                        ORDER BY total_energy_wh DESC
                    """,
                    "parameters": ["user_id"]
                },
                {
                    "purpose": "Get current device status",
                    "sql": """
                        SELECT DISTINCT ON (t.device_id) 
                               t.device_id, 
                               d.name as device_name,
                               t.energy_watts,
                               t.timestamp
                        FROM telemetry t
                        LEFT JOIN devices d ON t.device_id = d.device_id AND t.user_id = d.user_id
                        WHERE t.user_id = %s 
                          AND t.timestamp >= NOW() - INTERVAL '10 minutes'
                        ORDER BY t.device_id, t.timestamp DESC
                    """,
                    "parameters": ["user_id"]
                }
            ])
        
        return {
            "queries": queries,
            "explanation": f"Generated {len(queries)} fallback queries for: {user_message}"
        }

    async def _execute_sql_queries(self, sql_queries: Dict[str, Any], user: AuthUser) -> Dict[str, Any]:
        """Execute the generated SQL queries and return the results"""
        try:
            results = {}
            data_sources = []
            
            async for db in get_db():
                for i, query_info in enumerate(sql_queries.get("queries", [])):
                    try:
                        # Replace parameter placeholders with actual values
                        sql = query_info["sql"]
                        
                        # Replace both %s and $USER_ID with actual user_id
                        sql = sql.replace("%s", f"'{user.id}'")
                        sql = sql.replace("$USER_ID", f"'{user.id}'")
                        
                        # Execute the query using SQLAlchemy text()
                        result = await db.execute(text(sql))
                        rows = result.fetchall()
                        
                        # Convert to list of dictionaries
                        if rows:
                            columns = result.keys()
                            query_results = [dict(zip(columns, row)) for row in rows]
                            results[f"query_{i}"] = {
                                "purpose": query_info["purpose"],
                                "data": query_results,
                                "row_count": len(query_results)
                            }
                            data_sources.append(query_info["purpose"])
                            logger.info(f"Query {i} executed successfully: {len(query_results)} rows")
                        else:
                            results[f"query_{i}"] = {
                                "purpose": query_info["purpose"],
                                "data": [],
                                "row_count": 0
                            }
                    
                    except Exception as e:
                        logger.error(f"Error executing query {i}: {e}")
                        results[f"query_{i}"] = {
                            "purpose": query_info.get("purpose", "Unknown"),
                            "error": str(e),
                            "data": []
                        }
                
                break
                
            return {
                "results": results,
                "data_sources": data_sources,
                "explanation": sql_queries.get("explanation", ""),
                "query_count": len(sql_queries.get("queries", []))
            }
            
        except Exception as e:
            logger.error(f"Error executing SQL queries: {e}")
            return {
                "results": {},
                "data_sources": [],
                "error": str(e),
                "query_count": 0
            }

    async def _generate_data_analysis_response(self, user_message: str, fetched_data: Dict[str, Any]) -> str:
        """Generate final response using OpenAI with the fetched data"""
        try:
            # Prepare the data context for OpenAI
            data_context = json.dumps(fetched_data, indent=2, default=str)
            
            message = f"""User Query: {user_message}

Based on the user's query, I have fetched specific data from the database. Please analyze this data and provide a comprehensive, personalized response.

FETCHED DATA:
{data_context}

Please provide a detailed analysis that:
1. Directly answers the user's question using the specific data provided
2. Highlights key insights and patterns from the data
3. Provides actionable recommendations based on the findings
4. Uses concrete numbers and metrics from the actual data
5. Explains any notable trends or anomalies
6. Suggests optimization opportunities where relevant

Focus on being specific and data-driven rather than generic."""
            
            messages = [
                {"role": "system", "content": self.data_analysis_prompt},
                {"role": "user", "content": message}
            ]
            
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=settings.OPENAI_TEMPERATURE,
                max_tokens=2000,  # Limit response length to prevent overly long responses
                timeout=30
            )
            
            response_content = response.choices[0].message.content.strip()
            
            # Additional safety check for response length
            max_response_length = 7500  # Leave buffer for conversation history
            if len(response_content) > max_response_length:
                response_content = response_content[:max_response_length] + "... [Response truncated for optimal display]"
                logger.warning(f"AI response truncated: original length exceeded {max_response_length} characters")
            
            return response_content
            
        except Exception as e:
            logger.error(f"Error generating data analysis response: {e}")
            return await self._generate_fallback_analysis_response(user_message, fetched_data)

    async def _generate_fallback_analysis_response(self, user_message: str, fetched_data: Dict[str, Any]) -> str:
        """Generate fallback response when OpenAI is unavailable"""
        try:
            response_parts = []
            results = fetched_data.get("results", {})
            
            for query_key, query_result in results.items():
                purpose = query_result.get("purpose", "Data analysis")
                data = query_result.get("data", [])
                
                if data:
                    response_parts.append(f"**{purpose}:**")
                    
                    # Handle different types of data
                    if "device" in purpose.lower():
                        # Device-related data
                        for row in data[:5]:  # Limit to top 5
                            device_name = row.get("device_name") or row.get("device_id", "Unknown")
                            if "energy_wh" in str(row) or "total_energy_wh" in str(row):
                                energy = row.get("total_energy_wh", 0)
                                avg_watts = row.get("avg_watts", 0)
                                response_parts.append(f"• {device_name}: {energy:.1f} Wh (avg {avg_watts:.1f}W)")
                            elif "energy_watts" in str(row):
                                current_watts = row.get("energy_watts", 0)
                                timestamp = row.get("timestamp", "")
                                response_parts.append(f"• {device_name}: {current_watts:.1f}W currently")
                    
                    elif "trend" in purpose.lower() or "day" in str(data[0].keys()):
                        # Trend data
                        total_energy = sum(row.get("daily_energy_wh", 0) for row in data)
                        avg_daily = total_energy / len(data) if data else 0
                        response_parts.append(f"• Total energy over period: {total_energy:.1f} Wh")
                        response_parts.append(f"• Average daily consumption: {avg_daily:.1f} Wh")
                    
                    response_parts.append("")  # Add spacing
            
            if response_parts:
                base_response = "Based on your energy data analysis:\n\n" + "\n".join(response_parts)
                
                # Add general recommendations
                base_response += "\n**Recommendations:**\n"
                base_response += "• Monitor your highest consuming devices for optimization opportunities\n"
                base_response += "• Consider scheduling high-energy devices during off-peak hours\n"
                base_response += "• Track consumption patterns to identify potential savings\n"
                
                return base_response
            else:
                return "I analyzed your energy data but found limited recent information. " \
                       "Please ensure your devices are actively reporting data for more detailed insights."
                       
        except Exception as e:
            logger.error(f"Error generating fallback analysis response: {e}")
            return "I encountered an issue analyzing your energy data. Please try rephrasing your question or check that your devices are reporting data properly."

    def _generate_intelligent_suggestions(self, fetched_data: Dict[str, Any], user_message: str) -> List[str]:
        """Generate intelligent suggestions based on the fetched data"""
        suggestions = []
        
        try:
            results = fetched_data.get("results", {})
            
            # Analyze the type of data we have to generate relevant suggestions
            has_device_data = any("device" in result.get("purpose", "").lower() for result in results.values())
            has_trend_data = any("trend" in result.get("purpose", "").lower() or "day" in result.get("purpose", "").lower() for result in results.values())
            has_realtime_data = any("real-time" in result.get("purpose", "").lower() or "current" in result.get("purpose", "").lower() for result in results.values())
            
            if has_device_data:
                suggestions.extend([
                    "How can I optimize my highest consuming device?",
                    "Compare device efficiency over different time periods",
                    "Show me device usage patterns this week"
                ])
            
            if has_trend_data:
                suggestions.extend([
                    "What's causing changes in my energy consumption?",
                    "Predict my energy usage for next week",
                    "Compare this month vs last month"
                ])
            
            if has_realtime_data:
                suggestions.extend([
                    "Which devices should I turn off right now?",
                    "What's my peak consumption time today?",
                    "Show me hourly usage breakdown"
                ])
            
            # Default suggestions if no specific patterns found
            if not suggestions:
                suggestions = [
                    "Show me my energy usage trends",
                    "Which device uses the most energy?",
                    "Give me energy-saving recommendations"
                ]
            
            # Return top 3 unique suggestions
            return list(dict.fromkeys(suggestions))[:3]
            
        except Exception as e:
            logger.warning(f"Error generating intelligent suggestions: {e}")
            return [
                "Show me my current energy consumption",
                "Which device consumes the most energy?",
                "Give me personalized energy-saving tips"
            ]
    
    async def _fetch_comprehensive_data(self, user: AuthUser) -> Dict[str, Any]:
        """Fallback method to fetch comprehensive data when intelligent workflow fails"""
        try:
            comprehensive_data = {}
            data_sources = []
            
            # Get real-time metrics
            try:
                realtime_metrics = await self.telemetry_client.get_realtime_metrics(user)
                if realtime_metrics:
                    comprehensive_data["realtime_metrics"] = realtime_metrics
                    data_sources.append("Real-time device metrics")
            except Exception as e:
                logger.warning(f"Failed to fetch real-time metrics: {e}")
            
            # Get recent energy summary
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            try:
                summary = await self.telemetry_client.get_energy_summary(user, yesterday.isoformat(), now.isoformat())
                if summary:
                    comprehensive_data["energy_summaries"] = {"last_24_hours": summary}
                    data_sources.append("24-hour energy summary")
            except Exception as e:
                logger.warning(f"Failed to fetch energy summary: {e}")
            
            return {
                "data": comprehensive_data,
                "data_sources": data_sources,
                "fetch_timestamp": now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching comprehensive data: {e}")
            return {
                "data": {},
                "data_sources": [],
                "fetch_timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }

    def _calculate_insights(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate derived insights from the comprehensive data"""
        insights = {}
        
        try:
            # Energy efficiency trends
            if "energy_summaries" in data:
                summaries = data["energy_summaries"]
                if "last_24_hours" in summaries and "last_7_days" in summaries:
                    daily_avg = summaries["last_24_hours"].get("total_energy_wh", 0)
                    weekly_daily_avg = summaries["last_7_days"].get("total_energy_wh", 0) / 7
                    
                    if weekly_daily_avg > 0:
                        trend_ratio = daily_avg / weekly_daily_avg
                        if trend_ratio > 1.2:
                            insights["energy_trend"] = "increasing"
                        elif trend_ratio < 0.8:
                            insights["energy_trend"] = "decreasing"
                        else:
                            insights["energy_trend"] = "stable"
                        insights["trend_ratio"] = trend_ratio
            
            # Device efficiency ranking
            if "device_statistics" in data:
                device_efficiency = []
                for device_id, device_data in data["device_statistics"].items():
                    if "last_24_hours" in device_data:
                        stats = device_data["last_24_hours"]
                        efficiency_score = stats.get("total_energy_wh", 0) / max(stats.get("avg_energy_watts", 1), 1)
                        device_efficiency.append({
                            "device_id": device_id,
                            "efficiency_score": efficiency_score,
                            "total_energy": stats.get("total_energy_wh", 0)
                        })
                
                if device_efficiency:
                    device_efficiency.sort(key=lambda x: x["total_energy"], reverse=True)
                    insights["device_ranking"] = device_efficiency
                    insights["highest_consumer"] = device_efficiency[0]["device_id"] if device_efficiency else None
            
            # Cost estimates (assuming $0.12/kWh)
            if "energy_summaries" in data:
                for period, summary in data["energy_summaries"].items():
                    energy_kwh = summary.get("total_energy_wh", 0) / 1000
                    estimated_cost = energy_kwh * 0.12
                    insights[f"estimated_cost_{period}"] = round(estimated_cost, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating insights: {e}")
            insights["calculation_error"] = str(e)
        
        return insights

    async def _generate_comprehensive_response(self, request: ChatRequest, user: AuthUser, token: str, conversation_id: str) -> ChatResponse:
        """Generate response by fetching comprehensive data and using AI for intelligent analysis"""
        try:
            # Fetch all available data
            data_result = await self._fetch_comprehensive_data(user)
            comprehensive_data = data_result["data"]
            data_sources = data_result["data_sources"]
            
            # Generate AI response with comprehensive data
            if self.openai_available:
                response_text = await self._generate_openai_response_with_data(request.message, comprehensive_data)
            else:
                response_text = await self._generate_fallback_response_with_data(request.message, comprehensive_data)
            
            # Generate contextual suggested questions based on available data
            suggested_questions = self._generate_contextual_suggestions(comprehensive_data, request.message)
            
            return ChatResponse(
                message=response_text,
                conversation_id=conversation_id,
                timestamp=datetime.utcnow(),
                data_sources=data_sources if data_sources else None,
                confidence=0.9,  # High confidence since we have comprehensive data
                suggested_questions=suggested_questions
            )
            
        except Exception as e:
            logger.error(f"Error generating comprehensive response: {e}")
            return ChatResponse(
                message="I encountered an issue while analyzing your energy data. Please try again in a moment.",
                conversation_id=conversation_id,
                timestamp=datetime.utcnow(),
                confidence=0.0
            )

    async def _generate_openai_response_with_data(self, message: str, comprehensive_data: Dict[str, Any]) -> str:
        """Generate response using OpenAI with comprehensive data context"""
        try:
            # Prepare comprehensive context for OpenAI
            context_text = ""
            if comprehensive_data:
                context_text = f"\n\nCOMPREHENSIVE ENERGY DATA CONTEXT:\n{json.dumps(comprehensive_data, indent=2, default=str)}"
            
            # user message with data context
            message = f"""User Query: {message}

Please analyze the comprehensive energy data provided and give a detailed, personalized response that:
1. Directly addresses the user's question using actual data
2. Provides specific insights based on the available metrics
3. Offers actionable recommendations when appropriate
4. Highlights any notable patterns or anomalies
5. Includes relevant comparisons across time periods or devices
6. Calculates potential savings or efficiency improvements where applicable

Use the real data to provide concrete, valuable insights rather than generic advice.{context_text}"""
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": message}
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
            return await self._generate_fallback_response_with_data(message, comprehensive_data)

    async def _generate_fallback_response_with_data(self, message: str, comprehensive_data: Dict[str, Any]) -> str:
        """Generate fallback response with comprehensive data when OpenAI is not available"""
        try:
            response_parts = []
            
            # Analyze real-time metrics
            if "realtime_metrics" in comprehensive_data:
                realtime = comprehensive_data["realtime_metrics"]
                active_devices = realtime.get("active_devices", 0)
                total_power = realtime.get("total_current_power", 0)
                highest_device = realtime.get("highest_consuming_device")
                
                response_parts.append(f"**Current Status**: {active_devices} active devices consuming {total_power:.1f}W total")
                if highest_device:
                    response_parts.append(f"**Highest Consumer**: {highest_device.replace('-', ' ').title()}")
            
            # Analyze energy summaries
            if "energy_summaries" in comprehensive_data:
                summaries = comprehensive_data["energy_summaries"]
                if "last_24_hours" in summaries:
                    daily = summaries["last_24_hours"]
                    response_parts.append(
                        f"**24-Hour Summary**: {daily.get('total_energy_wh', 0):.1f} Wh consumed "
                        f"across {daily.get('total_devices', 0)} devices"
                    )
            
            # Analyze device statistics
            if "device_statistics" in comprehensive_data:
                device_stats = comprehensive_data["device_statistics"]
                top_consumers = []
                for device_id, data in device_stats.items():
                    if "last_24_hours" in data:
                        stats = data["last_24_hours"]
                        top_consumers.append({
                            "device": device_id.replace("-", " ").title(),
                            "energy": stats.get("total_energy_wh", 0)
                        })
                
                if top_consumers:
                    top_consumers.sort(key=lambda x: x["energy"], reverse=True)
                    response_parts.append(
                        f"**Top Energy Consumer**: {top_consumers[0]['device']} "
                        f"({top_consumers[0]['energy']:.1f} Wh in 24h)"
                    )
            
            # Analyze insights
            if "insights" in comprehensive_data:
                insights = comprehensive_data["insights"]
                if "energy_trend" in insights:
                    trend = insights["energy_trend"]
                    response_parts.append(f"**Energy Trend**: Your consumption is {trend}")
                
                if "estimated_cost_last_24_hours" in insights:
                    cost = insights["estimated_cost_last_24_hours"]
                    response_parts.append(f"**Estimated Daily Cost**: ${cost:.2f}")
            
            if response_parts:
                base_response = "Based on your comprehensive energy data:\n\n" + "\n\n".join(response_parts)
                
                # Add recommendations
                base_response += "\n\n**Recommendations**:\n"
                base_response += "• Monitor your highest consuming device for optimization opportunities\n"
                base_response += "• Consider turning off devices when not in use\n"
                base_response += "• Track your energy trends to identify patterns\n"
                base_response += "• Focus energy-saving efforts on your top consumers for maximum impact"
                
                return base_response
            else:
                return "I've analyzed your energy system but found limited recent data. " \
                       "Please ensure your devices are actively reporting telemetry data for more detailed insights."
                       
        except Exception as e:
            logger.error(f"Error generating fallback response with data: {e}")
            return "I'm analyzing your energy data to provide personalized insights. " \
                   "Please ensure your smart home devices are connected and reporting data."

    def _generate_contextual_suggestions(self, comprehensive_data: Dict[str, Any], message: str) -> List[str]:
        """Generate contextual suggested questions based on available data"""
        suggestions = []
        
        try:
            # Base suggestions
            base_suggestions = [
                "What's my current energy consumption?",
                "Which device uses the most energy?",
                "How can I reduce my energy costs?",
                "Show me my energy trends this week",
                "Give me personalized energy-saving tips"
            ]
            
            # Contextual suggestions based on data
            if "realtime_metrics" in comprehensive_data:
                realtime = comprehensive_data["realtime_metrics"]
                if realtime.get("highest_consuming_device"):
                    device = realtime["highest_consuming_device"].replace("-", " ")
                    suggestions.append(f"How can I optimize my {device}?")
            
            if "insights" in comprehensive_data:
                insights = comprehensive_data["insights"]
                if insights.get("energy_trend") == "increasing":
                    suggestions.append("Why is my energy consumption increasing?")
                elif insights.get("energy_trend") == "decreasing":
                    suggestions.append("What's helping reduce my energy usage?")
            
            if "device_statistics" in comprehensive_data:
                suggestions.append("Compare my device efficiency")
                suggestions.append("Show me device usage patterns")
            
            # Return mix of contextual and base suggestions
            all_suggestions = suggestions + base_suggestions
            return list(dict.fromkeys(all_suggestions))[:3]  # Remove duplicates and limit to 3
            
        except Exception as e:
            logger.warning(f"Error generating contextual suggestions: {e}")
            return [
                "Show me my energy usage today",
                "Which device consumes the most energy?",
                "Give me energy-saving recommendations"
            ]
    
    
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
