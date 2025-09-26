from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    get_password_hash,
    decode_token,
    get_current_user_id,
    create_api_response,
    check_rate_limit
)
from app.db.base import get_database
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
    PasswordChange
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/register", response_model=dict)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_database),
    _: bool = Depends(check_rate_limit)
):
    """Register a new user"""
    try:
        # Check if user already exists
        result = await db.execute(
            select(User).where(User.email == user_create.email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        # Create new user
        hashed_password = get_password_hash(user_create.password)
        db_user = User(
            email=user_create.email,
            name=user_create.name,
            hashed_password=hashed_password,
            role=user_create.role
        )

        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        logger.info("User registered", user_id=str(db_user.id), email=db_user.email)

        return create_api_response(
            success=True,
            data=UserResponse.from_orm(db_user),
            message="User registered successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Registration failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=dict)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_database),
    _: bool = Depends(check_rate_limit)
):
    """Authenticate user and return access token"""
    try:
        # Find user by email (username field contains email)
        result = await db.execute(
            select(User).where(User.email == form_data.username)
        )
        user = result.scalar_one_or_none()

        # Verify user exists and password is correct
        if not user or not verify_password(form_data.password, user.hashed_password):
            logger.warning("Login attempt failed", email=form_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )

        # Create access and refresh tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=str(user.id),
            expires_delta=access_token_expires
        )

        refresh_token = create_refresh_token(subject=str(user.id))

        # Update last login time
        from sqlalchemy import func
        user.last_login = func.now()
        await db.commit()

        logger.info("User logged in", user_id=str(user.id), email=user.email)

        return create_api_response(
            success=True,
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": UserResponse.from_orm(user)
            },
            message="Login successful"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/refresh", response_model=dict)
async def refresh_token(
    token_data: dict,
    db: AsyncSession = Depends(get_database),
    _: bool = Depends(check_rate_limit)
):
    """Refresh access token using refresh token"""
    try:
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token is required"
            )

        # Decode and validate refresh token
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Verify user still exists and is active
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Create new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=str(user.id),
            expires_delta=access_token_expires
        )

        return create_api_response(
            success=True,
            data={
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            },
            message="Token refreshed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token refresh failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.get("/me", response_model=dict)
async def get_current_user(
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get current user information"""
    try:
        result = await db.execute(select(User).where(User.id == current_user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return create_api_response(
            success=True,
            data=UserResponse.from_orm(user)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get current user failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )


@router.put("/me", response_model=dict)
async def update_profile(
    user_update: UserUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Update current user profile"""
    try:
        result = await db.execute(select(User).where(User.id == current_user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Update user fields
        if user_update.name is not None:
            user.name = user_update.name

        if user_update.email is not None:
            # Check if email is already taken
            existing_user_result = await db.execute(
                select(User).where(User.email == user_update.email, User.id != current_user_id)
            )
            if existing_user_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already taken"
                )
            user.email = user_update.email

        await db.commit()
        await db.refresh(user)

        logger.info("User profile updated", user_id=str(user.id))

        return create_api_response(
            success=True,
            data=UserResponse.from_orm(user),
            message="Profile updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Profile update failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )


@router.post("/change-password", response_model=dict)
async def change_password(
    password_change: PasswordChange,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Change user password"""
    try:
        result = await db.execute(select(User).where(User.id == current_user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify current password
        if not verify_password(password_change.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Update password
        user.hashed_password = get_password_hash(password_change.new_password)
        await db.commit()

        logger.info("Password changed", user_id=str(user.id))

        return create_api_response(
            success=True,
            message="Password changed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Password change failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


@router.post("/logout", response_model=dict)
async def logout(current_user_id: str = Depends(get_current_user_id)):
    """Logout user (mainly for logging purposes since JWT is stateless)"""
    logger.info("User logged out", user_id=current_user_id)

    return create_api_response(
        success=True,
        message="Logged out successfully"
    )