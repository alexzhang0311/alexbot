from typing import Optional, List, Dict, Any, AsyncGenerator
import httpx
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models import LLMProvider, User
from app.core.config import get_settings


class LLMService:
    """
    Unified LLM service that supports multiple providers:
    - OpenAI compatible (OpenAI, Minimax, local models, etc.)
    - Anthropic compatible (Claude via API proxy)
    """

    PROVIDER_TYPES = ["openai", "anthropic", "claude_agent", "custom"]

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: Dict[str, LLMProvider] = {}

    async def _get_provider(self, provider_id: str = None, user_id: str = None) -> Optional[LLMProvider]:
        """Get provider by ID, or default provider for user"""
        if provider_id:
            return await self._get_provider_by_id(provider_id)
        return await self._get_default_provider(user_id)

    async def _get_provider_by_id(self, provider_id: str) -> Optional[LLMProvider]:
        if provider_id in self._cache:
            return self._cache[provider_id]
        result = await self.db.execute(
            select(LLMProvider).where(
                and_(LLMProvider.id == provider_id, LLMProvider.is_active == True)
            )
        )
        provider = result.scalar_one_or_none()
        if provider:
            self._cache[provider_id] = provider
        return provider

    async def _get_default_provider(self, user_id: str = None) -> Optional[LLMProvider]:
        """Get default provider for a user, or global default"""
        query = select(LLMProvider).where(
            and_(LLMProvider.is_active == True, LLMProvider.is_default == True)
        )
        result = await self.db.execute(query)
        provider = result.scalar_one_or_none()
        
        # If no default, get first active
        if not provider:
            result = await self.db.execute(
                select(LLMProvider).where(LLMProvider.is_active == True).limit(1)
            )
            provider = result.scalar_one_or_none()
        
        return provider

    def _get_model_name(self, provider: LLMProvider, model_type: str = "default") -> str:
        """Get model name for a given type"""
        models = provider.models or {}
        return models.get(model_type, models.get("default", ""))

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider_id: str = None,
        model_type: str = "default",
        user_id: str = None,
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Send chat request to LLM provider.
        Yields response chunks for streaming.
        """
        provider = await self._get_provider(provider_id, user_id)
        if not provider:
            yield "⚠️ 未配置 LLM Provider，请先在设置中配置。"
            return

        model_name = self._get_model_name(provider, model_type)
        if not model_name:
            yield f"⚠️ Provider '{provider.name}' 未配置 '{model_type}' 模型"
            return

        if provider.provider_type == "claude_agent":
            async for chunk in self._call_claude_agent(provider, model_name, messages, stream, **kwargs):
                yield chunk
        elif provider.provider_type == "anthropic":
            async for chunk in self._call_anthropic(provider, model_name, messages, stream, **kwargs):
                yield chunk
        else:
            async for chunk in self._call_openai_compatible(provider, model_name, messages, stream, **kwargs):
                yield chunk

    async def _call_claude_agent(
        self,
        provider: LLMProvider,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Call Claude Agent SDK (supports custom base_url + MiniMax proxy)"""
        from claude_agent_sdk import query, ClaudeAgentOptions
        import os

        system_prompt = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                filtered_messages.append(msg)

        env = dict(os.environ)
        if provider.api_key:
            env["ANTHROPIC_API_KEY"] = provider.api_key
        if provider.base_url:
            env["ANTHROPIC_BASE_URL"] = provider.base_url.rstrip("/")

        options = ClaudeAgentOptions(
            model=model,
            allowed_tools=[],  # No tools, pure text generation
            env=env,
            include_partial_messages=True,
            cli_path="/usr/local/bin/claude",
        )
        if system_prompt:
            options.system_prompt = system_prompt

        try:
            async for msg in query(prompt=filtered_messages[-1]["content"], options=options):
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            yield block.text
        except Exception as e:
            yield f"⚠️ Claude Agent SDK 错误: {str(e)}"

    async def _call_openai_compatible(
        self,
        provider: LLMProvider,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Call OpenAI-compatible endpoint"""
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        timeout = (provider.config or {}).get("timeout", 120)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{provider.base_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json={"model": model, "messages": messages, "stream": stream, **kwargs},
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        yield f"⚠️ LLM 请求失败 ({response.status_code}): {error_body.decode()}"
                        return

                    if stream:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                if line.strip() == "data: [DONE]":
                                    break
                                try:
                                    import json
                                    data = json.loads(line[6:])
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                except Exception:
                                    pass
                    else:
                        result = await response.json()
                        yield result.get("choices", [{}])[0].get("message", {}).get("content", "")

            except httpx.TimeoutException:
                yield "⚠️ LLM 请求超时"
            except Exception as e:
                yield f"⚠️ LLM 请求异常: {str(e)}"

    async def _call_anthropic(
        self,
        provider: LLMProvider,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Call Anthropic-compatible endpoint (e.g. Minimax proxy)"""
        headers = {"x-api-key": provider.api_key or "", "Content-Type": "application/json"}
        if provider.provider_type == "anthropic":
            headers["anthropic-version"] = "2023-06-01"

        # Convert messages format for Anthropic
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        max_tokens = (provider.config or {}).get("max_tokens", 4096)
        
        async with httpx.AsyncClient(timeout=(provider.config or {}).get("timeout", 120)) as client:
            try:
                payload = {
                    "model": model,
                    "messages": anthropic_messages,
                    "max_tokens": max_tokens,
                    "stream": stream,
                }
                if system_msg:
                    payload["system"] = system_msg

                async with client.stream(
                    "POST",
                    f"{provider.base_url.rstrip('/')}/v1/messages",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        yield f"⚠️ Anthropic 请求失败 ({response.status_code}): {error_body.decode()}"
                        return

                    if stream:
                        current_block_type = None  # 'thinking' or 'text'
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("event: "):
                                evt = line[6:].strip()
                                if evt == "message_stop":
                                    break
                                continue
                            if line.startswith("data: "):
                                try:
                                    import json
                                    data = json.loads(line[6:])
                                    block_type = data.get("type", "")
                                    if block_type == "content_block_delta":
                                        delta = data.get("delta", {})
                                        delta_type = delta.get("type", "")
                                        if delta_type == "text_delta":
                                            text = delta.get("text", "")
                                            if text:
                                                yield text
                                    elif block_type == "content_block_start":
                                        cb = data.get("content_block", {})
                                        current_block_type = cb.get("type")
                                except Exception:
                                    pass
                    else:
                        result = await response.json()
                        yield result.get("content", [{}])[0].get("text", "")

            except httpx.TimeoutException:
                yield "⚠️ Anthropic 请求超时"
            except Exception as e:
                yield f"⚠️ Anthropic 请求异常: {str(e)}"


class LLMProviderService:
    """CRUD operations for LLM providers"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> LLMProvider:
        provider = LLMProvider(
            id=str(uuid.uuid4()),
            name=data["name"],
            provider_type=data["provider_type"],
            base_url=data["base_url"],
            api_key=data.get("api_key"),
            is_default=data.get("is_default", False),
            models=data.get("models", {}),
            config=data.get("config", {}),
        )
        
        # If this is set as default, unset others
        if provider.is_default:
            await self.db.execute(
                update(LLMProvider).values(is_default=False)
            )
        
        self.db.add(provider)
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def list(self) -> List[LLMProvider]:
        result = await self.db.execute(
            select(LLMProvider).order_by(LLMProvider.is_default.desc(), LLMProvider.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, provider_id: str) -> Optional[LLMProvider]:
        result = await self.db.execute(
            select(LLMProvider).where(LLMProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def update(self, provider_id: str, data: dict) -> Optional[LLMProvider]:
        provider = await self.get(provider_id)
        if not provider:
            return None
        
        for key in ["name", "base_url", "api_key", "is_default", "models", "config", "is_active"]:
            if key in data:
                setattr(provider, key, data[key])
        
        # If setting as default, unset others
        if data.get("is_default"):
            await self.db.execute(
                update(LLMProvider).where(LLMProvider.id != provider_id).values(is_default=False)
            )
        
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def delete(self, provider_id: str) -> bool:
        provider = await self.get(provider_id)
        if not provider:
            return False
        await self.db.delete(provider)
        await self.db.flush()
        return True