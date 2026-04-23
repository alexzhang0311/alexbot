import uuid
from datetime import datetime, timezone
from typing import Optional, List, AsyncGenerator
from sqlalchemy import select, func, update, delete, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ChatSession, Message, User
from app.schemas import ChatRequest, MessageResponse
from app.core.config import get_settings
from app.services.memory_service import MemoryService
from app.services.skill_dispatcher import SkillDispatcher

settings = get_settings()


class ChatService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.memory_service = MemoryService(db, user)
        self.skill_dispatcher = SkillDispatcher(db, user)

    async def create_session(self, title: str = "新对话", model: str = None) -> ChatSession:
        session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=self.user.id,
            title=title,
            model=model or settings.DEFAULT_MODEL,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        result = await self.db.execute(
            select(ChatSession).where(
                and_(ChatSession.id == session_id, ChatSession.user_id == self.user.id)
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(self, include_archived: bool = False) -> List[ChatSession]:
        # Subquery for message count
        msg_count_subq = (
            select(Message.session_id, func.count(Message.id).label('msg_count'))
            .group_by(Message.session_id)
            .subquery()
        )
        query = (
            select(ChatSession, msg_count_subq.c.msg_count)
            .outerjoin(msg_count_subq, ChatSession.id == msg_count_subq.c.session_id)
            .where(ChatSession.user_id == self.user.id)
        )
        if not include_archived:
            query = query.where(ChatSession.is_archived == False)
        query = query.order_by(ChatSession.updated_at.desc())
        result = await self.db.execute(query)
        rows = result.all()
        if not isinstance(rows, list):
            rows = list(rows)
        sessions = []
        for row in rows:
            session = row[0]
            session._message_count = row[1] or 0
            sessions.append(session)
        return sessions

    async def get_session_messages(self, session_id: str, limit: int = 100) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        model: str = None,
        tokens_used: int = 0,
        metadata_data: dict = None
    ) -> Message:
        message = Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            model=model,
            tokens_used=tokens_used,
            extra_data=metadata_data or {},
        )
        self.db.add(message)
        
        # Update session updated_at
        await self.db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
        
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def chat(
        self, 
        request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """
        Main chat loop. Yields response chunks for streaming.
        Returns the full assistant message after streaming completes.
        """
        session = await self.get_session(request.session_id)
        if not session:
            raise ValueError("Session not found")

        # Build context: system prompt + memories + conversation history
        system_prompt = await self._build_system_prompt()
        
        # Get conversation history (last N messages)
        history = await self.get_session_messages(request.session_id, limit=20)
        
        # Build messages list for LLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        
        messages.append({"role": "user", "content": request.message})

        # Check if any skills should be triggered
        skill_results = await self.skill_dispatcher.check_and_execute(
            request.message, 
            skill_names=request.skill_names
        )
        
        full_response = ""
        metadata = {"skill_calls": []}
        
        if skill_results:
            # Skill(s) were triggered - use their output
            for skill_name, result in skill_results.items():
                full_response += f"\n\n[{skill_name}]\n{result}"
            metadata["skill_calls"] = list(skill_results.keys())
        else:
            # Call LLM
            async for chunk in self._call_llm(request.model or session.model or settings.DEFAULT_MODEL, messages):
                full_response += chunk
                yield chunk

        # Save user message
        await self.save_message(
            session_id=request.session_id,
            role="user",
            content=request.message,
            model=request.model or session.model,
        )

        # Determine actual model used (request.model takes priority over session.model)
        actual_model = request.model or session.model or settings.DEFAULT_MODEL

        # Save assistant response
        await self.save_message(
            session_id=request.session_id,
            role="assistant",
            content=full_response,
            model=actual_model,
            metadata_data=metadata,
        )

        # Update memory with conversation summary if significant
        await self.memory_service.update_from_conversation(request.message, full_response)

    async def _build_system_prompt(self) -> str:
        """Build system prompt incorporating user memories and preferences"""
        memories = await self.memory_service.get_relevant_memories("", limit=5)
        prefs = self.user.preferences or {}
        
        prompt = "你是一个有帮助的AI助手。"
        
        if memories:
            prompt += "\n\n用户背景信息:\n" + "\n".join([f"- {m.content}" for m in memories])
        
        if prefs.get("language"):
            prompt = f"请使用{prefs['language']}回复。" + prompt
        
        return prompt

    async def _call_llm(self, model: str, messages: list) -> AsyncGenerator[str, None]:
        """Call LLM using configured provider (OpenAI compatible or Anthropic)"""
        from app.services.llm_service import LLMService
        
        llm_svc = LLMService(self.db)
        model_type = self._get_model_type(model)
        
        async for chunk in llm_svc.chat(
            messages=messages,
            model_type=model_type,
            user_id=self.user.id,
            stream=True,
        ):
            yield chunk

    def _get_model_type(self, model: str) -> str:
        """Map model name to model type (default/opus/sonnet/haiku/vision)"""
        model_lower = model.lower()
        if "opus" in model_lower:
            return "opus"
        elif "sonnet" in model_lower:
            return "sonnet"
        elif "haiku" in model_lower:
            return "haiku"
        elif "vision" in model_lower or "4o" in model_lower or "gpt-4" in model_lower:
            return "vision"
        return "default"

    async def delete_session(self, session_id: str) -> bool:
        session = await self.get_session(session_id)
        if not session:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True
