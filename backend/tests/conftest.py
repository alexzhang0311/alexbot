import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.database import Base
from app.models import User, ChatSession, Message, LLMProvider


# In-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    from app.core.security import get_password_hash
    user = User(
        id="test-user-1",
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_provider(db_session):
    provider = LLMProvider(
        id="test-provider-1",
        name="Test Provider",
        provider_type="anthropic",
        base_url="https://api.test.com",
        api_key="test-key-123",
        is_default=True,
        models={"default": "test-model", "opus": "test-opus"},
        config={"timeout": 30, "max_tokens": 4096},
        is_active=True,
    )
    db_session.add(provider)
    await db_session.flush()
    await db_session.refresh(provider)
    return provider


@pytest_asyncio.fixture
async def test_session(db_session, test_user):
    session = ChatSession(
        id="test-session-1",
        user_id=test_user.id,
        title="Test Chat",
        model="test-model",
    )
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)
    return session


@pytest_asyncio.fixture
async def test_message(db_session, test_session):
    message = Message(
        id="test-message-1",
        session_id=test_session.id,
        role="user",
        content="Hello, test message",
        model="test-model",
        tokens_used=10,
        extra_data={},
    )
    db_session.add(message)
    await db_session.flush()
    await db_session.refresh(message)
    return message
