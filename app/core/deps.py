from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import User
from app.schemas.user import TokenData
from app.core.redis_client import redis_service, conversation_cache
from app.core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AuthUser:
    """User information for unified service"""
    def __init__(self, user_id: str, email: str, role: str, name: str):
        self.id = user_id
        self.email = email
        self.role = role
        self.name = name


async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Extract JWT token from request"""
    return credentials.credentials


async def get_current_user_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    response: Response = None
) -> TokenData:
    """Extract and verify JWT token with automatic refresh"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        token_data, new_token = verify_token(token)
        
        if token_data is None:
            raise credentials_exception
        
        # If a new token was generated, add it to response headers
        if new_token and response:
            response.headers["X-New-Token"] = new_token
            logger.info(f"Token refreshed for user {token_data.user_id}")
            
        return token_data
        
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise credentials_exception


async def get_current_user(
    token_data: TokenData = Depends(get_current_user_token_data),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from database"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Check if user is blacklisted (token revoked)
        blacklist_key = f"blacklist:token:{token_data.user_id}"
        is_blacklisted = await redis_service.exists(blacklist_key)
        
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        
        # Get user from database
        stmt = select(User).where(User.id == token_data.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user is None:
            raise credentials_exception
            
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user"
            )
            
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User authentication error: {e}")
        raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> AuthUser:
    """Get current active user as AuthUser object"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return AuthUser(
        user_id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        name=current_user.name
    )


async def get_current_admin_user(
    current_user: AuthUser = Depends(get_current_active_user)
) -> AuthUser:
    """Get current admin user"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


class RateLimiter:
    """Rate limiting dependency"""
    
    def __init__(self):
        self.max_requests = settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = settings.RATE_LIMIT_WINDOW_MS
    
    async def __call__(self, request: Request) -> None:
        """Check rate limit for IP address"""
        client_ip = request.client.host
        key = f"rate_limit:{client_ip}"
        
        try:
            # Get current request count
            current_requests = await redis_service.get(key)
            
            if current_requests is None:
                # First request in window
                await redis_service.set(key, "1", expire=self.window_seconds)
            else:
                current_count = int(current_requests)
                
                if current_count >= self.max_requests:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded"
                    )
                
                # Increment counter
                await redis_service.increment(key)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Don't block requests if rate limiting fails
            pass


class UserRateLimiter:
    """User-based rate limiting dependency"""
    
    def __init__(self):
        self.max_requests = settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = settings.RATE_LIMIT_WINDOW_MS
    
    async def __call__(self, request: Request, current_user: AuthUser = Depends(get_current_active_user)) -> None:
        """Check rate limit for user"""
        endpoint = request.url.path
        
        try:
            # Get current usage count
            current_count = await conversation_cache.increment_usage_counter(current_user.id, endpoint)
            
            if current_count > self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds // 3600} hour(s)"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Don't block requests if rate limiting fails
            pass


# Rate limiter instances
auth_rate_limiter = RateLimiter()
general_rate_limiter = RateLimiter()
chat_rate_limiter = UserRateLimiter()
telemetry_rate_limiter = UserRateLimiter()

async def check_user_permissions(
    current_user: AuthUser,
    required_role: Optional[str] = None,
    resource_owner_id: Optional[str] = None
) -> bool:
    """Check if user has required permissions"""
    
    # Admin users have all permissions
    if current_user.role == "admin":
        return True
    
    # Check role requirement
    if required_role and current_user.role != required_role:
        return False
    
    # Check resource ownership
    if resource_owner_id and str(current_user.id) != resource_owner_id:
        return False
    
    return True


async def require_permissions(
    current_user: AuthUser = Depends(get_current_active_user),
    required_role: Optional[str] = None,
    resource_owner_id: Optional[str] = None
) -> AuthUser:
    """Dependency to require specific permissions"""
    
    has_permission = await check_user_permissions(
        current_user, required_role, resource_owner_id
    )
    
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return current_user


# Optional authentication for public endpoints
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[AuthUser]:
    """Get current user if token is provided, otherwise return None"""
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        token_data = verify_token(token)
        if token_data:
            return AuthUser(
                user_id=token_data.user_id,
                email=token_data.email,
                role=token_data.role,
                name="Unknown"  # We don't have name in token
            )
        return None
    except Exception:
        return None
