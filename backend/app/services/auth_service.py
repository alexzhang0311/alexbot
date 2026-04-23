import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, decode_token
from app.models import User
from app.schemas import UserCreate, UserResponse

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    
    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    # Check if username or email exists
    result = await db.execute(
        select(User).where((User.username == user_data.username) | (User.email == user_data.email))
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    user = User(
        id=str(uuid.uuid4()),
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession, skip: int = 0, limit: int = 50) -> List[User]:
    result = await db.execute(select(User).offset(skip).limit(limit))
    return list(result.scalars().all())
