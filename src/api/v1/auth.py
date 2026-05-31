from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.schemas.user import UserCreate, UserLogin, UserResponse, UserUpdate, Token
from src.schemas.auth import RefreshRequest
from src.services.auth_service import AuthService
from sqlalchemy import select
from src.core.security import (
    get_current_active_user, verify_password, verify_token, create_access_token,
    create_refresh_token
)
from src.models.user import User

router = APIRouter()
# router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new user
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (minimum 6 characters)
    - **full_name**: Optional full name
    """
    user = await AuthService.register_user(user_data, db)
    # return user
    return UserResponse.model_validate(user)
    

@router.post("/login", response_model=Token)
async def login(payload: UserLogin, db: Session = Depends(get_db)):

    user = await AuthService.authenticate_user(payload, db)  # ← must await
    return AuthService.create_tokens(user)

    # user = AuthService.authenticate_user(payload, db)
    # tokens = AuthService.create_tokens(user)
    # return tokens

@router.post("/refresh", response_model=Token)
async def refresh_token(
        payload: RefreshRequest,
        db: AsyncSession = Depends(get_db)
    ):
    user = await AuthService.verify_refresh_token(payload.refresh_token, db)
    return AuthService.create_tokens(user)

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_active_user)):
    return UserResponse.model_validate(current_user)

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    # For JWT, logout is typically handled on the client side by deleting the token.
    # Optionally, you can implement token blacklisting here.
    return {"message": "Successfully logged out"}