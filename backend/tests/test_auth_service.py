"""
Tests for auth_service
"""
import pytest
from app.services.auth_service import (
    authenticate_user, create_user, get_user_by_id, list_users
)
from app.schemas import UserCreate
from sqlalchemy import select


@pytest.mark.asyncio
async def test_create_user(db_session):
    """Test user creation"""
    user_data = UserCreate(
        username="newuser",
        email="new@example.com",
        full_name="New User",
        password="securepassword123"
    )
    user = await create_user(db_session, user_data)
    
    assert user.id is not None
    assert user.username == "newuser"
    assert user.email == "new@example.com"
    assert user.hashed_password != "securepassword123"  # should be hashed


@pytest.mark.asyncio
async def test_create_duplicate_user_fails(db_session, test_user):
    """Test that creating duplicate username/email fails"""
    user_data = UserCreate(
        username="testuser",  # same as test_user
        email="another@example.com",
        password="password123"
    )
    with pytest.raises(Exception):  # HTTPException
        await create_user(db_session, user_data)


@pytest.mark.asyncio
async def test_authenticate_user_success(db_session, test_user):
    """Test successful authentication"""
    user = await authenticate_user(db_session, "testuser", "password123")
    assert user is not None
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(db_session, test_user):
    """Test authentication with wrong password"""
    user = await authenticate_user(db_session, "testuser", "wrongpassword")
    assert user is None


@pytest.mark.asyncio
async def test_authenticate_user_not_found(db_session):
    """Test authentication with non-existent user"""
    user = await authenticate_user(db_session, "nonexistent", "password")
    assert user is None


@pytest.mark.asyncio
async def test_get_user_by_id(db_session, test_user):
    """Test getting user by ID"""
    user = await get_user_by_id(db_session, test_user.id)
    assert user is not None
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(db_session):
    """Test getting non-existent user"""
    user = await get_user_by_id(db_session, "nonexistent-id")
    assert user is None


@pytest.mark.asyncio
async def test_list_users(db_session, test_user):
    """Test listing users"""
    users = await list_users(db_session)
    assert len(users) >= 1
    assert any(u.username == "testuser" for u in users)
