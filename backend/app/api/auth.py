from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas import UserCreate, UserResponse, LoginRequest, Token
from app.services.auth_service import (
    authenticate_user, create_user, get_current_user, list_users
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, user_data)
    return user


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, login_data.username, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 50,
    _: User = Depends(get_current_user)  # require auth
):
    # In production, this should be admin-only
    users = await list_users(db, skip, limit)
    return users
