from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging

from app.core.config import settings
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Password hashing error: {e}")
        raise


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    try:
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT token creation error: {e}")
        raise


def verify_token(token: str) -> Tuple[Optional[TokenData], Optional[str]]:
    """Verify and decode JWT token with explicit expiration checking"""
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Check token expiration explicitly
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            current_time = datetime.utcnow()
            
            if current_time > exp_datetime:
                logger.warning(f"Token expired at {exp_datetime}, current time: {current_time}")
                return None, None
        
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        
        if user_id is None:
            return None, None
            
        token_data = TokenData(
            user_id=user_id,
            email=email,
            role=role
        )
        
        new_token_data = {
            "sub": user_id,
            "email": email,
            "role": role
        }
        new_token = create_access_token(new_token_data)
        return token_data, new_token
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return None, None


def create_password_reset_token(email: str) -> str:
    """Create password reset token"""
    data = {
        "sub": email,
        "type": "password_reset"
    }
    expires_delta = timedelta(hours=1)  # Reset token expires in 1 hour
    return create_access_token(data, expires_delta)


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and return email"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if email is None or token_type != "password_reset":
            return None
            
        return email
        
    except JWTError as e:
        logger.warning(f"Password reset token verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Password reset token verification error: {e}")
        return None


def generate_token_response(user_data: dict) -> dict:
    """Generate complete token response"""
    access_token_expires = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    
    token_data = {
        "sub": str(user_data["id"]),
        "email": user_data["email"],
        "role": user_data["role"]
    }
    
    access_token = create_access_token(
        data=token_data,
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60,  # Convert to seconds
        "user": user_data
    }
