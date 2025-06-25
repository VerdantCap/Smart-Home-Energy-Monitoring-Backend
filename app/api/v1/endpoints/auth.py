from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app.core.database import get_db
from app.core.deps import (
    get_current_user,
    get_current_active_user, 
    get_current_admin_user,
    auth_rate_limiter,
    general_rate_limiter
)
from app.core.security import generate_token_response, create_password_reset_token, verify_password_reset_token
from app.schemas.user import (
    UserCreate, 
    UserLogin, 
    Token, 
    UserResponse, 
    UserUpdate,
    PasswordChange,
    PasswordReset,
    PasswordResetConfirm,
    UserProfile
)
from app.models.user import User
from app.services.user_service import get_user_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limiter)
):
    """Register a new user"""
    try:
        user_service = get_user_service(db)
        
        # Create user
        user = await user_service.create_user(user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Generate token response
        user_dict = user.to_dict()
        token_response = generate_token_response(user_dict)
        
        logger.info(f"User registered successfully: {user.email}")
        return Token(**token_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limiter)
):
    """Authenticate user and return JWT token"""
    try:
        user_service = get_user_service(db)
        
        # Authenticate user
        user = await user_service.authenticate_user(login_data.email, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Generate token response
        user_dict = user.to_dict()
        token_response = generate_token_response(user_dict)
        
        logger.info(f"User logged in successfully: {user.email}")
        return Token(**token_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Get current user profile"""
    return UserProfile.model_validate(current_user)


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile"""
    try:
        user_service = get_user_service(db)
        
        # Check email availability if email is being updated
        if user_update.email and user_update.email != current_user.email:
            is_available = await user_service.is_email_available(
                user_update.email, 
                exclude_user_id=current_user.id
            )
            if not is_available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
        
        # Update user
        updated_user = await user_service.update_user(current_user.id, user_update)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Update failed"
            )
        
        logger.info(f"User profile updated: {current_user.email}")
        return UserProfile.model_validate(updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    try:
        user_service = get_user_service(db)
        
        success = await user_service.change_password(
            current_user.id,
            password_data.current_password,
            password_data.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        logger.info(f"Password changed for user: {current_user.email}")
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


@router.post("/password-reset")
async def request_password_reset(
    request: Request,
    reset_data: PasswordReset,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limiter)
):
    """Request password reset"""
    try:
        user_service = get_user_service(db)
        
        # Check if user exists
        user = await user_service.get_user_by_email(reset_data.email)
        if not user:
            # Don't reveal if email exists or not
            return {"message": "If the email exists, a reset link has been sent"}
        
        # Generate reset token
        reset_token = create_password_reset_token(reset_data.email)
        
        # In a real application, you would send this token via email
        # For demo purposes, we'll return it in the response
        logger.info(f"Password reset requested for: {reset_data.email}")
        
        return {
            "message": "Password reset token generated",
            "reset_token": reset_token  # Remove this in production
        }
        
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        return {"message": "If the email exists, a reset link has been sent"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limiter)
):
    """Confirm password reset with token"""
    try:
        # Verify reset token
        email = verify_password_reset_token(reset_data.token)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        user_service = get_user_service(db)
        
        # Reset password
        success = await user_service.reset_password(email, reset_data.new_password)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset failed"
            )
        
        logger.info(f"Password reset completed for: {email}")
        return {"message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout user (revoke all tokens)"""
    try:
        user_service = get_user_service(db)
        
        # Revoke all user tokens
        await user_service.revoke_all_user_tokens(current_user.id)
        
        logger.info(f"User logged out: {current_user.email}")
        return {"message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


# Admin endpoints
@router.get("/users", response_model=List[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(general_rate_limiter)
):
    """Get list of users (admin only)"""
    try:
        user_service = get_user_service(db)
        users = await user_service.get_users(skip=skip, limit=limit)
        
        return [UserResponse.model_validate(user) for user in users]
        
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user (admin only)"""
    try:
        user_service = get_user_service(db)
        
        # Check email availability if email is being updated
        if user_update.email:
            is_available = await user_service.is_email_available(
                user_update.email, 
                exclude_user_id=user_id
            )
            if not is_available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
        
        # Update user
        updated_user = await user_service.update_user(user_id, user_update)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"User updated by admin: {user_id}")
        return UserResponse.model_validate(updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin user update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User update failed"
        )


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate user (admin only)"""
    try:
        user_service = get_user_service(db)
        
        success = await user_service.deactivate_user(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"User deactivated by admin: {user_id}")
        return {"message": "User deactivated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User deactivation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User deactivation failed"
        )
