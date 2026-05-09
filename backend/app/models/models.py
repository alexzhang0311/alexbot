from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(256), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(128))
    avatar_url = Column(String(512))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # User preferences stored as JSON
    preferences = Column(JSON, default=dict)
    
    # Relationships
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    scheduled_tasks = relationship("ScheduledTask", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    title = Column(String(256), default="新对话")
    model = Column(String(64), default="default")  # model key, resolved via provider
    provider_id = Column(String(64), nullable=True)  # specific LLM provider
    tools_enabled = Column(Boolean, default=True)     # enable agent tools (bash, file ops, skills)
    is_pinned = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(32), nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False)
    model = Column(String(64))
    tokens_used = Column(Integer, default=0)
    extra_data = Column(JSON, default=dict)  # skill_calls, attachments, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")


class UserMemory(Base):
    """Long-term user memory / user profile"""
    __tablename__ = "user_memories"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    memory_type = Column(String(64), nullable=False)  # preference, habit, fact, summary
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=5)  # 1-10
    last_accessed = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="memories")


class Skill(Base):
    """Available skills / plugins"""
    __tablename__ = "skills"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(Text)
    category = Column(String(64))  # productivity, data, communication, etc.
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # skill-specific config
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    task_type = Column(String(64), nullable=False)  # reminder, recurring, one_time
    cron_expression = Column(String(128))  # for recurring tasks
    payload = Column(JSON, nullable=False)  # task-specific data
    is_active = Column(Boolean, default=True)
    next_run = Column(DateTime(timezone=True))
    last_run = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="scheduled_tasks")


class LLMProvider(Base):
    """LLM Provider configuration"""
    __tablename__ = "llm_providers"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)  # e.g. "Minimax", "OpenAI", "Custom"
    provider_type = Column(String(32), nullable=False)  # openai / anthropic / claude_agent / custom
    base_url = Column(String(512), nullable=False)
    api_key = Column(String(256))
    is_default = Column(Boolean, default=False)
    models = Column(JSON, default=dict)  # {"default": "qwen3.5", "opus": "...", ...}
    config = Column(JSON, default=dict)  # extra config (timeout, etc.)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
