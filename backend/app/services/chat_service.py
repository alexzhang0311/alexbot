import uuid
import os
import re
from datetime import datetime, timezone
from typing import Optional, List, AsyncGenerator
from loguru import logger
from sqlalchemy import select, func, update, delete, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ChatSession, Message, User, LLMProvider
from app.schemas import ChatRequest, MessageResponse, SessionUpdate
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

    async def create_session(
        self, title: str = "新对话", model: str = None,
        provider_id: str = None, tools_enabled: bool = True
    ) -> ChatSession:
        session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=self.user.id,
            title=title,
            model=model or settings.DEFAULT_MODEL,
            provider_id=provider_id,
            tools_enabled=tools_enabled,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def update_session(self, session_id: str, data: SessionUpdate) -> Optional[ChatSession]:
        """Update session settings (provider, model, tools toggle, etc.)"""
        session = await self.get_session(session_id)
        if not session:
            return None
        updates = {}
        for field in ["title", "model", "provider_id", "tools_enabled", "is_pinned", "is_archived"]:
            val = getattr(data, field, None)
            if val is not None:
                updates[field] = val
        if updates:
            await self.db.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(**updates, updated_at=datetime.now(timezone.utc))
            )
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

    async def _resolve_provider(self, provider_id: str = None) -> Optional[LLMProvider]:
        """Resolve which provider to use: explicit > session > default."""
        from app.services.llm_service import LLMService
        llm_svc = LLMService(self.db)
        if provider_id:
            return await llm_svc._get_provider_by_id(provider_id)
        return await llm_svc._get_default_provider(self.user.id)

    async def _get_provider_type(self, provider_id: str = None) -> str:
        """Get provider_type for the resolved provider."""
        provider = await self._resolve_provider(provider_id)
        if provider:
            return provider.provider_type
        return "openai"

    async def _resolve_model(self, model_key: str, provider_id: str = None) -> str:
        """Resolve actual model name from provider config."""
        provider = await self._resolve_provider(provider_id)
        if provider and provider.models:
            model_type = self._get_model_type(model_key)
            return provider.models.get(model_type, provider.models.get("default", model_key))
        return model_key

    async def chat(
        self, 
        request: ChatRequest,
        _tool_collector: list = None,
        _user_input_handler=None,
    ) -> AsyncGenerator[str, None]:
        """
        Main chat loop. Yields response chunks for streaming.
        Returns the full assistant message after streaming completes.
        """
        session = await self.get_session(request.session_id)
        if not session:
            raise ValueError("Session not found")

        request_id = str(uuid.uuid4())[:8]
        logger.info(
            f"[CHAT][{request_id}] start user_id={self.user.id} session_id={request.session_id} "
            f"request_model={request.model} provider_id={request.provider_id}"
        )

        # Resolve provider: request > session > default
        provider_id = request.provider_id or session.provider_id
        provider_type = await self._get_provider_type(provider_id)

        # Resolve model: resolve model_key through provider to get actual model name
        model_key = request.model or session.model or settings.DEFAULT_MODEL
        actual_model = await self._resolve_model(model_key, provider_id)

        # Resolve tools_enabled: request > session > default=True
        tools_enabled = request.tools_enabled
        if tools_enabled is None:
            tools_enabled = session.tools_enabled if session.tools_enabled is not None else True

        # Build context: system prompt + memories + conversation history
        system_prompt = await self._build_system_prompt(
            provider_type if tools_enabled else ""
        )
        
        # Get conversation history (last N messages)
        history = await self.get_session_messages(request.session_id, limit=20)
        
        # Build messages list for LLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        
        messages.append({"role": "user", "content": request.message})

        full_response = ""
        metadata = {"skill_calls": []}

        if provider_type == "claude_agent" and tools_enabled:
            logger.info(f"[CHAT][{request_id}] route=claude_agent tools_enabled={tools_enabled}")
            # Claude Agent SDK mode: model decides tool usage autonomously
            async for chunk in self._call_llm(
                actual_model,
                messages,
                provider_id=provider_id,
                tools_enabled=True,
                _tool_collector=_tool_collector,
                user_input_handler=_user_input_handler,
                request_id=request_id,
            ):
                full_response += chunk
                yield chunk
            
            # Capture tool calls in metadata
            if _tool_collector:
                metadata["tool_calls"] = _tool_collector
                metadata["skill_calls"] = [t for t in _tool_collector if t.startswith("skill-") or t in ("weather","calculator","reminder","qa")]
        else:
            logger.info(f"[CHAT][{request_id}] route=skill_dispatch_or_llm tools_enabled={tools_enabled}")
            # Non-agent mode: check keyword skills first, fallback to LLM
            skill_results = await self.skill_dispatcher.check_and_execute(
                request.message, 
                skill_names=request.skill_names
            )
            
            valid_skill_results = {
                name: result for name, result in skill_results.items() 
                if result and result.strip()
            }
            
            if valid_skill_results:
                for skill_name, result in valid_skill_results.items():
                    full_response += f"\n\n[{skill_name}]\n{result}"
                metadata["skill_calls"] = list(valid_skill_results.keys())
            
            if not valid_skill_results:
                async for chunk in self._call_llm(
                    actual_model,
                    messages,
                    provider_id=provider_id,
                    tools_enabled=False,
                    request_id=request_id,
                ):
                    full_response += chunk
                    yield chunk
        
        # Streaming complete - generator will finish after this
        # DB save will happen after generator ends (but won't block it)
        logger.info(
            f"[CHAT][{request_id}] streaming complete, scheduling DB save session_id={request.session_id}"
        )

    async def _build_system_prompt(self, provider_type: str = "") -> str:
        """Build system prompt incorporating user memories and preferences"""
        memories = await self.memory_service.get_relevant_memories("", limit=5)
        prefs = self.user.preferences or {}
        
        # Dynamically load skills from .claude/skills/ directory
        skills_prompt = self._load_skills_prompt()
        
        if provider_type == "claude_agent":
            prompt = (
                "你是一个企业级 AI 助手。\n"
                "\n"
                "## 可用技能 (始终激活，不要说未激活)\n"
                "\n"
                + skills_prompt +
                "\n## 工具\n"
                "Read/Write/Edit(文件) Bash(命令) Glob/Grep(搜索)\n"
                "\n"
                "## 规则\n"
                "1. 技能始终可用，绝不说'技能未激活'\n"
                "2. 使用技能后标注: <!-- skill:技能名 -->\n"
                "3. 主动用技能和工具高效回答"
            )
        else:
            prompt = (
                "你是一个有帮助的AI助手。\n"
                "你可以回答用户问题，进行计算、天气查询、提醒设置等。\n"
                "使用技能后标注: <!-- skill:技能名 -->"
            )
        
        if memories:
            prompt += "\n\n用户背景信息:\n" + "\n".join([f"- {m.content}" for m in memories])
        
        if prefs.get("language"):
            prompt = f"请使用{prefs['language']}回复。" + prompt
        
        return prompt

    def _load_skills_prompt(self) -> str:
        """Dynamically load all skill descriptions from .claude/skills/ directory.
        
        Reads SKILL.md files at request time, so adding/modifying skills
        takes effect immediately without restart.
        """
        skills_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "skills")
        skills_dir = os.path.abspath(skills_dir)
        
        if not os.path.isdir(skills_dir):
            return ""
        
        lines = []
        for entry in sorted(os.listdir(skills_dir)):
            skill_path = os.path.join(skills_dir, entry, "SKILL.md")
            if not os.path.isfile(skill_path):
                continue
            
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Parse YAML frontmatter
                name = entry
                desc = ""
                fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    for fm_line in fm_match.group(1).split("\n"):
                        kv = fm_line.split(":", 1)
                        if len(kv) == 2:
                            key, val = kv[0].strip(), kv[1].strip()
                            if key == "name":
                                name = val
                            elif key == "description":
                                desc = val
                
                # Build a concise one-liner for the prompt
                skill_line = f"### /{name} - {desc}" if desc else f"### /{name}"
                lines.append(skill_line)
                
                # Include body summary (first non-empty line after frontmatter)
                body = re.sub(r"^---\s*\n.*?\n---\s*\n*", "", content, flags=re.DOTALL)
                body_summary = ""
                for bl in body.split("\n"):
                    bl = bl.strip()
                    if bl and not bl.startswith("#"):
                        body_summary = bl[:120]
                        break
                if body_summary:
                    lines.append(f"  {body_summary}")
                
            except Exception:
                pass
        
        return "\n".join(lines) if lines else ""

    async def _call_llm(self, model: str, messages: list, **kwargs) -> AsyncGenerator[str, None]:
        """Call LLM using configured provider (OpenAI compatible or Anthropic)"""
        from app.services.llm_service import LLMService
        
        llm_svc = LLMService(self.db)
        model_type = self._get_model_type(model)
        
        async for chunk in llm_svc.chat(
            messages=messages,
            model_type=model_type,
            user_id=self.user.id,
            stream=True,
            **kwargs,
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
