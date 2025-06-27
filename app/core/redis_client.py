import redis.asyncio as redis
import logging
from typing import Optional
import json

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global Redis client
redis_client: Optional[redis.Redis] = None


async def init_redis() -> None:
    """Initialize Redis connection"""
    global redis_client
    
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Test connection
        await redis_client.ping()
        logger.info("Redis connection established successfully")
        
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    if redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return redis_client


async def close_redis() -> None:
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed")


class RedisService:
    """Redis service for caching and session management"""
    
    def __init__(self):
        self.client = None
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client"""
        if not self.client:
            self.client = await get_redis()
        return self.client
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis"""
        try:
            client = await self.get_client()
            result = await client.set(key, value, ex=expire)
            return result
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from Redis"""
        try:
            client = await self.get_client()
            return await client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        try:
            client = await self.get_client()
            result = await client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        try:
            client = await self.get_client()
            result = await client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis EXISTS error: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a key's value"""
        try:
            client = await self.get_client()
            return await client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error: {e}")
            return None
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for a key"""
        try:
            client = await self.get_client()
            result = await client.expire(key, seconds)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis EXPIRE error: {e}")
            return False


class ConversationCache:
    """Redis-based conversation cache for AI service"""
    
    def __init__(self):
        self.client = None
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client"""
        if not self.client:
            self.client = await get_redis()
        return self.client
    
    async def get_conversation(self, user_id: str) -> Optional[dict]:
        """Get conversation history for a user"""
        try:
            client = await self.get_client()
            key = f"conversation:{user_id}"
            data = await client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return None
    
    async def save_conversation(self, user_id: str, conversation: dict) -> bool:
        """Save conversation history for a user"""
        try:
            client = await self.get_client()
            key = f"conversation:{user_id}"
            
            # Set expiration based on conversation timeout
            expire_seconds = settings.CONVERSATION_TIMEOUT_MINUTES * 60
            
            result = await client.set(
                key, 
                json.dumps(conversation), 
                ex=expire_seconds
            )
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return False
    
    async def add_message(self, user_id: str, role: str, content: str) -> bool:
        """Add a message to conversation history"""
        try:
            conversation = await self.get_conversation(user_id) or {
                "messages": [],
                "created_at": None,
                "updated_at": None
            }
            
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            
            # Truncate content if it exceeds the maximum length (8000 chars from schema)
            max_content_length = 7900  # Leave some buffer for safety
            if len(content) > max_content_length:
                truncated_content = content[:max_content_length] + "... [Message truncated due to length]"
                logger.warning(f"Message truncated for user {user_id}: original length {len(content)}, truncated to {len(truncated_content)}")
                content = truncated_content
            
            # Add new message
            conversation["messages"].append({
                "role": role,
                "content": content,
                "timestamp": now
            })
            
            # Keep only the last N messages
            if len(conversation["messages"]) > settings.MAX_CONVERSATION_HISTORY:
                conversation["messages"] = conversation["messages"][-settings.MAX_CONVERSATION_HISTORY:]
            
            # Update timestamps
            if not conversation["created_at"]:
                conversation["created_at"] = now
            conversation["updated_at"] = now
            
            return await self.save_conversation(user_id, conversation)
            
        except Exception as e:
            logger.error(f"Error adding message to conversation: {e}")
            return False
    
    async def clear_conversation(self, user_id: str) -> bool:
        """Clear conversation history for a user"""
        try:
            client = await self.get_client()
            key = f"conversation:{user_id}"
            result = await client.delete(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
            return False
    
    async def cache_query_result(self, query_hash: str, result: dict) -> bool:
        """Cache query result"""
        try:
            client = await self.get_client()
            key = f"query_cache:{query_hash}"
            
            result_json = json.dumps(result)
            success = await client.set(key, result_json, ex=settings.CACHE_TTL_SECONDS)
            return bool(success)
            
        except Exception as e:
            logger.error(f"Error caching query result: {e}")
            return False
    
    async def get_cached_query_result(self, query_hash: str) -> Optional[dict]:
        """Get cached query result"""
        try:
            client = await self.get_client()
            key = f"query_cache:{query_hash}"
            data = await client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached query result: {e}")
            return None
    
    async def increment_usage_counter(self, user_id: str, endpoint: str) -> int:
        """Increment usage counter for rate limiting"""
        try:
            client = await self.get_client()
            key = f"usage:{user_id}:{endpoint}"
            
            # Increment counter with expiration
            count = await client.incr(key)
            if count == 1:  # First increment, set expiration
                await client.expire(key, settings.RATE_LIMIT_WINDOW)
            
            return count
            
        except Exception as e:
            logger.error(f"Error incrementing usage counter: {e}")
            return 0
    
    async def get_usage_count(self, user_id: str, endpoint: str) -> int:
        """Get current usage count"""
        try:
            client = await self.get_client()
            key = f"usage:{user_id}:{endpoint}"
            count = await client.get(key)
            return int(count) if count else 0
            
        except Exception as e:
            logger.error(f"Error getting usage count: {e}")
            return 0


# Global service instances
redis_service = RedisService()
conversation_cache = ConversationCache()
