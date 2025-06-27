from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
import logging
import uuid

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password
from app.core.redis_client import redis_service

logger = logging.getLogger(__name__)


class UserService:
    """Service layer for user operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        """Create a new user"""
        try:
            # Check if user already exists
            existing_user = await self.get_user_by_email(user_data.email)
            if existing_user:
                return None
            
            # Hash password
            hashed_password = get_password_hash(user_data.password)
            
            # Create user
            db_user = User(
                email=user_data.email,
                password_hash=hashed_password,
                name=user_data.name,
                role=user_data.role or "user"
            )
            
            self.db.add(db_user)
            await self.db.commit()
            await self.db.refresh(db_user)
            
            logger.info(f"User created successfully: {user_data.email}")
            return db_user
            
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"User creation failed - integrity error: {e}")
            return None
        except Exception as e:
            await self.db.rollback()
            logger.error(f"User creation failed: {e}")
            raise
    
    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID"""
        try:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        try:
            stmt = select(User).where(User.email == email)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        try:
            user = await self.get_user_by_email(email)
            if not user:
                return None
            
            if not user.is_active:
                return None
            
            if not verify_password(password, user.password_hash):
                return None
            
            # Clear any existing token blacklist for this user upon successful login
            await self.clear_user_token_blacklist(user.id)
            
            logger.info(f"User authenticated successfully: {email}")
            return user
            
        except Exception as e:
            logger.error(f"Authentication error for {email}: {e}")
            return None
    
    async def update_user(self, user_id: uuid.UUID, user_data: UserUpdate) -> Optional[User]:
        """Update user information"""
        try:
            # Get existing user
            user = await self.get_user_by_id(user_id)
            if not user:
                return None
            
            # Update fields
            update_data = {}
            if user_data.name is not None:
                update_data["name"] = user_data.name
            if user_data.email is not None:
                update_data["email"] = user_data.email
            if user_data.is_active is not None:
                update_data["is_active"] = user_data.is_active
            if user_data.role is not None:
                update_data["role"] = user_data.role
            
            if not update_data:
                return user
            
            # Execute update
            stmt = update(User).where(User.id == user_id).values(**update_data)
            await self.db.execute(stmt)
            await self.db.commit()
            
            # Return updated user
            updated_user = await self.get_user_by_id(user_id)
            logger.info(f"User updated successfully: {user_id}")
            return updated_user
            
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"User update failed - integrity error: {e}")
            return None
        except Exception as e:
            await self.db.rollback()
            logger.error(f"User update failed: {e}")
            raise
    
    async def change_password(self, user_id: uuid.UUID, current_password: str, new_password: str) -> bool:
        """Change user password"""
        try:
            user = await self.get_user_by_id(user_id)
            if not user:
                return False
            
            # Verify current password
            if not verify_password(current_password, user.password_hash):
                return False
            
            # Hash new password
            new_password_hash = get_password_hash(new_password)
            
            # Update password
            stmt = update(User).where(User.id == user_id).values(password_hash=new_password_hash)
            await self.db.execute(stmt)
            await self.db.commit()
            
            # Invalidate all user tokens
            await self.revoke_all_user_tokens(user_id)
            
            logger.info(f"Password changed successfully for user: {user_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Password change failed for user {user_id}: {e}")
            return False
    
    async def reset_password(self, email: str, new_password: str) -> bool:
        """Reset user password"""
        try:
            user = await self.get_user_by_email(email)
            if not user:
                return False
            
            # Hash new password
            new_password_hash = get_password_hash(new_password)
            
            # Update password
            stmt = update(User).where(User.id == user.id).values(password_hash=new_password_hash)
            await self.db.execute(stmt)
            await self.db.commit()
            
            # Invalidate all user tokens
            await self.revoke_all_user_tokens(user.id)
            
            logger.info(f"Password reset successfully for user: {email}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Password reset failed for user {email}: {e}")
            return False
    
    async def deactivate_user(self, user_id: uuid.UUID) -> bool:
        """Deactivate user account"""
        try:
            stmt = update(User).where(User.id == user_id).values(is_active=False)
            result = await self.db.execute(stmt)
            await self.db.commit()
            
            if result.rowcount > 0:
                # Revoke all user tokens
                await self.revoke_all_user_tokens(user_id)
                logger.info(f"User deactivated successfully: {user_id}")
                return True
            
            return False
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"User deactivation failed: {e}")
            return False
    
    async def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get list of users with pagination"""
        try:
            stmt = select(User).offset(skip).limit(limit)
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
    
    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> bool:
        """Revoke all tokens for a user by adding to blacklist"""
        try:
            blacklist_key = f"blacklist:token:{user_id}"
            # Set blacklist entry with long expiration (longer than max token lifetime)
            await redis_service.set(blacklist_key, "revoked", expire=86400 * 7)  # 7 days
            logger.info(f"All tokens revoked for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Token revocation failed for user {user_id}: {e}")
            return False
    
    async def clear_user_token_blacklist(self, user_id: uuid.UUID) -> bool:
        """Clear token blacklist for a user upon successful login"""
        try:
            blacklist_key = f"blacklist:token:{user_id}"
            await redis_service.delete(blacklist_key)
            logger.info(f"Token blacklist cleared for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear token blacklist for user {user_id}: {e}")
            return False
    
    async def is_email_available(self, email: str, exclude_user_id: Optional[uuid.UUID] = None) -> bool:
        """Check if email is available for use"""
        try:
            stmt = select(User).where(User.email == email)
            if exclude_user_id:
                stmt = stmt.where(User.id != exclude_user_id)
            
            result = await self.db.execute(stmt)
            existing_user = result.scalar_one_or_none()
            
            return existing_user is None
            
        except Exception as e:
            logger.error(f"Error checking email availability: {e}")
            return False


def get_user_service(db: AsyncSession) -> UserService:
    """Dependency to get user service"""
    return UserService(db)
