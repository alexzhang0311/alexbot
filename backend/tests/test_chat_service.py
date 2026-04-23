"""
Tests for chat_service
"""
import pytest
from app.services.chat_service import ChatService
from app.models import ChatSession
from sqlalchemy import select


@pytest.mark.asyncio
async def test_create_session(db_session, test_user):
    """Test creating a new chat session"""
    chat_svc = ChatService(db_session, test_user)
    session = await chat_svc.create_session(title="My Chat", model="test-model")
    
    assert session.id is not None
    assert session.title == "My Chat"
    assert session.model == "test-model"
    assert session.user_id == test_user.id


@pytest.mark.asyncio
async def test_get_session(db_session, test_user, test_session):
    """Test getting a session by ID"""
    chat_svc = ChatService(db_session, test_user)
    session = await chat_svc.get_session(test_session.id)
    
    assert session is not None
    assert session.id == test_session.id


@pytest.mark.asyncio
async def test_get_session_wrong_user(db_session, test_user):
    """Test that users cannot see other users' sessions"""
    from app.models import User
    from app.core.security import get_password_hash
    
    # Create another user with a session
    other_user = User(
        id="other-user",
        username="other",
        email="other@example.com",
        hashed_password=get_password_hash("password"),
    )
    db_session.add(other_user)
    await db_session.flush()
    
    other_session = ChatSession(id="other-session", user_id=other_user.id, title="Private")
    db_session.add(other_session)
    await db_session.flush()
    
    # First user should not see other's session
    chat_svc = ChatService(db_session, test_user)
    session = await chat_svc.get_session("other-session")
    assert session is None


@pytest.mark.asyncio
async def test_list_sessions(db_session, test_user, test_session):
    """Test listing sessions for a user"""
    chat_svc = ChatService(db_session, test_user)
    
    # Create another session
    await chat_svc.create_session(title="Second Chat")
    
    sessions = await chat_svc.list_sessions()
    assert len(sessions) >= 2


@pytest.mark.asyncio
async def test_save_message(db_session, test_user, test_session):
    """Test saving a message"""
    chat_svc = ChatService(db_session, test_user)
    message = await chat_svc.save_message(
        session_id=test_session.id,
        role="user",
        content="Test message",
        model="test-model",
        tokens_used=5,
        metadata_data={"source": "test"},
    )
    
    assert message.id is not None
    assert message.content == "Test message"
    assert message.role == "user"
    assert message.extra_data == {"source": "test"}


@pytest.mark.asyncio
async def test_get_session_messages(db_session, test_user, test_session, test_message):
    """Test getting messages for a session"""
    chat_svc = ChatService(db_session, test_user)
    messages = await chat_svc.get_session_messages(test_session.id)
    
    assert len(messages) >= 1
    assert messages[0].content == "Hello, test message"


@pytest.mark.asyncio
async def test_delete_session(db_session, test_user, test_session):
    """Test deleting a session"""
    chat_svc = ChatService(db_session, test_user)
    
    result = await chat_svc.delete_session(test_session.id)
    assert result is True
    
    # Verify deleted
    session = await chat_svc.get_session(test_session.id)
    assert session is None


@pytest.mark.asyncio
async def test_delete_session_not_found(db_session, test_user):
    """Test deleting non-existent session"""
    chat_svc = ChatService(db_session, test_user)
    result = await chat_svc.delete_session("nonexistent-id")
    assert result is False
