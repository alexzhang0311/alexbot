from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.websocket import router as ws_router
from app.api.memory import router as memory_router
from app.api.tasks import router as tasks_router
from app.api.skills import router as skills_router
from app.api.llm import router as llm_router

__all__ = ["auth_router", "chat_router", "ws_router", "memory_router", "tasks_router", "skills_router"]
