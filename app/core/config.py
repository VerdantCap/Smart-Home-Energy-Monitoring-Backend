from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Unified application settings for Smart Home Energy Monitoring"""
    
    # Basic settings
    APP_NAME: str = "Smart Home Unified Service"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    
    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@postgres:5432/smart_home_energy"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Individual database components (for Docker)
    POSTGRES_DB: str = "smart_home_energy"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    # JWT settings
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-here-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # Redis settings
    REDIS_URL: str = "redis://redis:6379"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    # Security settings
    ALLOWED_HOSTS: List[str] = ["*"]
    BCRYPT_ROUNDS: int = 12
    
    # Rate limiting
    RATE_LIMIT_MAX_REQUESTS: int = 1000
    RATE_LIMIT_WINDOW_MS: int = 100
    RATE_LIMIT_WINDOW: int = 3600
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # OpenAI settings (for AI service functionality)
    OPENAI_API_KEY: str = "your-openai-api-key-here"
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_TEMPERATURE: float = 0.7
    
    # AI settings
    MAX_CONVERSATION_HISTORY: int = 10
    CONVERSATION_TIMEOUT_MINUTES: int = 30
    CACHE_TTL_SECONDS: int = 300  # 5 minutes
    
    # Query processing settings
    MAX_QUERY_LENGTH: int = 500
    SUPPORTED_TIME_RANGES: List[str] = ["today", "yesterday", "this week", "last week", "this month", "last month"]
    
    # Telemetry settings
    MAX_BATCH_SIZE: int = 1000
    BATCH_TIMEOUT_SECONDS: int = 30
    DATA_RETENTION_DAYS: int = 365
    
    # Analytics settings
    AGGREGATION_INTERVALS: List[str] = ["1h", "1d", "1w", "1M"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()
