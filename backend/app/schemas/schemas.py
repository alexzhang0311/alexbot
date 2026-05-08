from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── User ──
class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class UserResponse(UserBase):
    id: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    avatar_url: Optional[str] = None
    preferences: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


# ── Auth ──
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# ── Chat Session ──
class SessionBase(BaseModel):
    title: Optional[str] = "新对话"
    model: Optional[str] = "gpt-4o"


class SessionCreate(SessionBase):
    provider_id: Optional[str] = None
    tools_enabled: Optional[bool] = True


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None
    provider_id: Optional[str] = None
    tools_enabled: Optional[bool] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None


class SessionResponse(SessionBase):
    id: str
    user_id: str
    provider_id: Optional[str] = None
    tools_enabled: bool = True
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# ── Message ──
class MessageBase(BaseModel):
    content: str
    role: str  # user / assistant / system


class MessageCreate(MessageBase):
    session_id: str


class MessageResponse(MessageBase):
    id: str
    session_id: str
    model: Optional[str] = None
    tokens_used: int = 0
    extra_data: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Expose as 'metadata' for API compatibility
    @property
    def metadata(self) -> Dict[str, Any]:
        return self.extra_data


# ── Chat Request (WebSocket / streaming) ──
class ChatRequest(BaseModel):
    session_id: str
    message: str
    model: Optional[str] = None
    provider_id: Optional[str] = None      # use specific provider
    tools_enabled: Optional[bool] = None   # enable/disable agent tools
    stream: bool = True
    skill_names: Optional[List[str]] = None  # which skills to enable for this turn


# ── Memory ──
class MemoryCreate(BaseModel):
    memory_type: str
    content: str
    importance: int = 5


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[int] = None


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    memory_type: str
    content: str
    importance: int
    last_accessed: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Skill ──
class SkillResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_enabled: bool
    config: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


# ── Scheduled Task ──
class ScheduledTaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    task_type: str  # reminder, recurring, one_time
    cron_expression: Optional[str] = None
    payload: Dict[str, Any]


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    cron_expression: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ScheduledTaskResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    task_type: str
    cron_expression: Optional[str] = None
    is_active: bool
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ── LLM Provider ──
class LLMProviderCreate(BaseModel):
    name: str
    provider_type: str  # openai / anthropic / custom
    base_url: str
    api_key: Optional[str] = None
    is_default: bool = False
    models: Dict[str, Any] = {}
    config: Dict[str, Any] = {}


class LLMProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None
    models: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class LLMProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    is_default: bool
    models: Dict[str, Any]
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    # Mask api_key in response
    @property
    def api_key_masked(self) -> str:
        if not self.api_key:
            return None
        return self.api_key[:6] + "***" + self.api_key[-4:]
