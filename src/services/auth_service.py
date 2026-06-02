from datetime import datetime
from jose import JWTError, jwt
from src.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status, Depends
from src.database import get_db
from src.models.user import User, UserProfile, UserRoleMap
from src.schemas.user import UserCreate, UserLogin, Token
from src.core.security import (
    verify_password, hash_password, 
    create_access_token, create_refresh_token, verify_token
)


class AuthService:
    """Authentication service for user management"""

    @staticmethod
    async def register_user(payload: UserCreate, db: AsyncSession) -> User:
        result = await db.execute(select(User).where(User.email == payload.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        result = await db.execute(select(User).where(User.phone == payload.phone))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already registered")

        role_map = UserRoleMap(role=payload.role)
        profile = UserProfile(
            first_name=payload.first_name,
            last_name=payload.last_name,
        )

        user = User(
            email=payload.email,
            phone=payload.phone,
            hashed_password=hash_password(payload.password),
            roles=[role_map],
            profile=profile,
        )
        db.add(user)
        await db.flush()

        user_id = user.id

        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.roles),
                selectinload(User.profile),
            )
        )
        return result.scalar_one()
  
    
    @staticmethod
    async def authenticate_user(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> User:
        """Authenticate user by email/phone and password"""
        result = await db.execute(select(User)
                                  .where((User.email == payload.email) | (User.phone == payload.email))
                                  .options(
                                      selectinload(User.roles),
                                      selectinload(User.profile),
                                      )
                                    )
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        
        user.last_login = datetime.utcnow()
        await db.flush()
        
        return user

    
    @staticmethod
    def create_tokens(user: User) -> Token:
        payload = {"sub": user.email, "user_id": str(user.id)}  # UUID → str
        return Token(
            access_token=create_access_token(data=payload),
            refresh_token=create_refresh_token(data=payload),
            token_type="bearer",
        )
    
    @staticmethod
    async def verify_refresh_token(refresh_token: str, db: AsyncSession) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
        try:
            payload = jwt.decode(
                refresh_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            # payload is a plain dict from jwt.decode — use .get()
            if payload.get("type") != "refresh":
                raise credentials_exception

            user_id: str = payload.get("user_id")
            email: str = payload.get("sub")

            if not user_id or not email:
                raise credentials_exception

        except JWTError:
            raise credentials_exception

        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles), selectinload(User.profile))
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise credentials_exception

        return user