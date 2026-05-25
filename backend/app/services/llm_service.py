from typing import Optional, List, Dict, Any, AsyncGenerator
import json
import httpx
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from loguru import logger

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

    @staticmethod
    def _truncate_text(value: Any, max_len: int = 12000) -> Any:
        if isinstance(value, str) and len(value) > max_len:
            return value[:max_len] + f"... <truncated {len(value) - max_len} chars>"
        return value

    @classmethod
    def _sanitize_payload(cls, value: Any) -> Any:
        secret_keys = {
            "api_key", "apikey", "authorization", "anthropic_api_key", "token", "secret"
        }
        if isinstance(value, dict):
            sanitized = {}
            for k, v in value.items():
                if str(k).lower() in secret_keys:
                    sanitized[k] = "***"
                else:
                    sanitized[k] = cls._sanitize_payload(v)
            return sanitized
        if isinstance(value, list):
            return [cls._sanitize_payload(v) for v in value]
        return cls._truncate_text(value)

    @classmethod
    def _serialize_sdk_message(cls, msg: Any) -> str:
        try:
            if hasattr(msg, "model_dump"):
                payload = msg.model_dump()
            elif hasattr(msg, "dict"):
                payload = msg.dict()
            elif hasattr(msg, "__dict__"):
                payload = msg.__dict__
            else:
                payload = str(msg)
            return json.dumps(cls._sanitize_payload(payload), ensure_ascii=False, default=str)
        except Exception:
            return str(msg)

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
        request_id = kwargs.get("request_id", str(uuid.uuid4())[:8])
        # provider_id from kwargs takes priority over the parameter
        _pid = kwargs.pop("provider_id", None) or provider_id
        provider = await self._get_provider(_pid, user_id)
        if not provider:
            logger.warning(f"[LLM][{request_id}] No provider configured for user_id={user_id}")
            yield "⚠️ 未配置 LLM Provider，请先在设置中配置。"
            return

        model_name = self._get_model_name(provider, model_type)
        if not model_name:
            logger.warning(
                f"[LLM][{request_id}] Provider '{provider.name}' missing model_type='{model_type}'"
            )
            yield f"⚠️ Provider '{provider.name}' 未配置 '{model_type}' 模型"
            return

        logger.info(
            f"[LLM][{request_id}] provider={provider.provider_type} provider_id={provider.id} "
            f"model={model_name} stream={stream} messages={len(messages)}"
        )

        if provider.provider_type == "claude_agent":
            async for chunk in self._call_claude_agent(provider, model_name, messages, stream, **kwargs):
                yield chunk
        elif provider.provider_type == "anthropic":
            async for chunk in self._call_anthropic(provider, model_name, messages, stream, **kwargs):
                yield chunk
        else:
            async for chunk in self._call_openai_compatible(provider, model_name, messages, stream, **kwargs):
                yield chunk

    @staticmethod
    def _resolve_claude_cli(configured_path: str | None) -> str | None:
        """Resolve Claude CLI path.

        Returns:
            A valid CLI path, or None to let the SDK auto-detect
            (SDK checks bundled binary first, then system PATH).
        """
        import shutil
        import os as _os
        import platform

        # Paths that should never be passed to the SDK — let it auto-detect.
        default_paths = {"/usr/local/bin/claude", "/usr/bin/claude", "claude", None}

        if configured_path and configured_path not in default_paths:
            # On Windows, npm global installs create .CMD wrapper scripts that
            # don't work via anyio.open_process. Skip them — SDK's bundled
            # claude.exe is the real binary.
            if platform.system() == "Windows" and configured_path.lower().endswith(".cmd"):
                logger.warning(
                    f"Skipping .CMD wrapper '{configured_path}' — "
                    "SDK will use bundled claude.exe instead"
                )
                return None

            if _os.path.isfile(configured_path) or shutil.which(configured_path):
                return configured_path

            logger.warning(
                f"Configured cli_path '{configured_path}' not found, "
                "falling back to SDK auto-detect"
            )
            return None

        # No explicit path (or it's a default / .CMD wrapper) — let SDK auto-detect.
        # SDK's SubprocessCLITransport._find_cli() checks:
        #   1. Bundled binary (_bundled/claude or _bundled/claude.exe)
        #   2. shutil.which("claude")
        #   3. Common install paths
        # Passing any cli_path prevents SDK from finding the bundled CLI.
        return None

    async def _call_claude_agent(
        self,
        provider: LLMProvider,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Call Claude Agent SDK with tool support (skills, bash, file ops)"""
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, PermissionResultDeny
        import os
        import platform

        request_id = kwargs.get("request_id", str(uuid.uuid4())[:8])

        # Split system prompt from conversation messages
        system_prompt = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation.append(msg)

        # Build env with provider credentials
        env = dict(os.environ)
        if provider.api_key:
            env["ANTHROPIC_API_KEY"] = provider.api_key
        if provider.base_url:
            env["ANTHROPIC_BASE_URL"] = provider.base_url.rstrip("/")

        # Get tools config from provider config or use defaults
        provider_config = provider.config or {}
        tools_enabled = kwargs.get("tools_enabled", provider_config.get("tools_enabled", True))

        if tools_enabled:
            allowed_tools = provider_config.get("allowed_tools", [
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            ])
        else:
            allowed_tools = []

        user_input_handler = kwargs.get("user_input_handler")
        if tools_enabled and user_input_handler and "AskUserQuestion" not in allowed_tools:
            allowed_tools = [*allowed_tools, "AskUserQuestion"]

        async def _dummy_hook(input_data, tool_use_id, context):
            # Python SDK workaround from docs: keep stream open for can_use_tool
            return {"continue_": True}

        async def _can_use_tool(tool_name: str, input_data: dict, context):
            if not user_input_handler:
                return PermissionResultAllow(updated_input=input_data)

            logger.info(
                f"[ClaudeSDK][{request_id}] 🔔 触发 can_use_tool 回调 tool={tool_name}"
            )

            try:
                decision = await user_input_handler(tool_name, input_data, context)
            except Exception as e:
                logger.exception(f"[ClaudeSDK][{request_id}] user_input_handler failed: {e}")
                return PermissionResultDeny(message=f"用户输入处理失败: {e}")

            if isinstance(decision, dict):
                behavior = str(decision.get("behavior", "allow")).lower()
                if behavior == "deny":
                    logger.warning(
                        f"[ClaudeSDK][{request_id}] ❌ 用户拒绝工具调用 tool={tool_name} "
                        f"message={decision.get('message', 'User denied this action')}"
                    )
                    return PermissionResultDeny(
                        message=decision.get("message", "User denied this action")
                    )
                logger.info(
                    f"[ClaudeSDK][{request_id}] ✅ 用户批准工具调用 tool={tool_name}"
                )
                return PermissionResultAllow(
                    updated_input=decision.get("updated_input", input_data)
                )

            # Default fallback: allow as-is
            logger.info(f"[ClaudeSDK][{request_id}] ✅ 默认允许 tool={tool_name}")
            return PermissionResultAllow(updated_input=input_data)

        # Resolve CLI path.
        # Only pass cli_path if it's a validated, existing path.
        # When None, SDK auto-detects (bundled CLI → system PATH → common paths).
        resolved_cli = self._resolve_claude_cli(
            provider_config.get("cli_path")
        )
        resolved_cwd = provider_config.get("cwd", os.getcwd())

        # Capture stderr for better error diagnostics
        stderr_lines = []
        def _stderr_cb(line: str):
            stderr_lines.append(line)
            logger.warning(f"[ClaudeSDK][{request_id}][stderr] {line}")

        # Build options — only set cli_path when we have a verified path
        options_kwargs: dict = {
            "model": model,
            "allowed_tools": allowed_tools,
            "skills": ["weather", "calculator", "reminder", "qa"],
            "permission_mode": "bypassPermissions",
            "env": env,
            "include_partial_messages": True,
            "stderr": _stderr_cb,
            "cwd": resolved_cwd,
        }
        if user_input_handler:
            if str(options_kwargs.get("permission_mode", "")).lower() == "bypasspermissions":
                # When user interaction is enabled, switch from bypass to interactive mode
                options_kwargs["permission_mode"] = provider_config.get("interactive_permission_mode", "default")
            options_kwargs["can_use_tool"] = _can_use_tool
            options_kwargs["hooks"] = {
                "PreToolUse": [
                    HookMatcher(matcher=None, hooks=[_dummy_hook])
                ]
            }
            logger.info(
                f"[ClaudeSDK][{request_id}] user_input_handler enabled, permission_mode={options_kwargs['permission_mode']}"
            )
        if resolved_cli:
            options_kwargs["cli_path"] = resolved_cli
            logger.info(f"[ClaudeSDK][{request_id}] using explicit cli_path={resolved_cli}")
        else:
            logger.info(f"[ClaudeSDK][{request_id}] no cli_path set, SDK auto-detect (bundled → PATH)")

        options = ClaudeAgentOptions(**options_kwargs)
        if system_prompt:
            options.system_prompt = system_prompt

        # Build user prompt: include last N conversation turns for context
        user_prompt = self._build_agent_prompt(conversation)

        tool_collector = kwargs.get("_tool_collector", None)
        logger.info(
            f"[ClaudeSDK][{request_id}] start model={model} cwd={resolved_cwd} "
            f"tools_enabled={tools_enabled} tools={len(allowed_tools)}"
        )

        raw_request_payload = {
            "prompt": user_prompt,
            "options": {
                "model": options_kwargs.get("model"),
                "allowed_tools": options_kwargs.get("allowed_tools"),
                "skills": options_kwargs.get("skills"),
                "permission_mode": options_kwargs.get("permission_mode"),
                "can_use_tool": bool(user_input_handler),
                "include_partial_messages": options_kwargs.get("include_partial_messages"),
                "cwd": options_kwargs.get("cwd"),
                "cli_path": options_kwargs.get("cli_path"),
                "env": {
                    "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL"),
                    "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY"),
                },
                "system_prompt": system_prompt,
            },
        }
        logger.info(
            "[ClaudeSDK][{}] raw request -> {}".format(
                request_id,
                json.dumps(self._sanitize_payload(raw_request_payload), ensure_ascii=False, default=str),
            )
        )

        def _build_prompt_input():
            if user_input_handler:
                async def _prompt_stream():
                    yield {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": user_prompt,
                        },
                    }

                return _prompt_stream()
            return user_prompt

        if platform.system() == "Windows":
            # Windows: ensure Proactor loop policy for subprocess support.
            # Run SDK's query() in a dedicated thread with asyncio.run(),
            # matching the demo script pattern (fresh event loop, no uvicorn).
            import threading
            import queue as _q
            import asyncio as _aio

            logger.info(f"[ClaudeSDK][{request_id}] running in thread (Windows)")
            msg_queue: _q.Queue = _q.Queue()

            def _run_sdk() -> None:
                _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())

                async def _inner() -> None:
                    try:
                        async for msg in query(
                            prompt=_build_prompt_input(), options=options
                        ):
                            msg_queue.put(("msg", msg))
                        msg_queue.put(("done", None))
                    except Exception as exc:
                        import traceback
                        msg_queue.put(("error", (exc, traceback.format_exc())))

                _aio.run(_inner())

            thread = threading.Thread(target=_run_sdk, daemon=True)
            thread.start()

            while True:
                try:
                    kind, payload = msg_queue.get(timeout=0.2)
                except _q.Empty:
                    await _aio.sleep(0.05)
                    continue

                if kind == "done":
                    logger.info(f"[ClaudeSDK][{request_id}] query() completed (thread)")
                    return
                if kind == "error":
                    e, worker_tb = payload
                    cause = e
                    cause_chain = []
                    while cause is not None:
                        cause_chain.append(
                            f"{type(cause).__name__}: {cause}"
                        )
                        cause = cause.__cause__
                        if len(cause_chain) > 5:
                            break
                    logger.exception(f"[ClaudeSDK][{request_id}] failed: {e}")
                    logger.error(
                        f"Cause chain: {' ← '.join(cause_chain)}"
                    )
                    err_detail = str(e)
                    if stderr_lines:
                        err_detail += (
                            "\n\nSTDERR:\n"
                            + "\n".join(stderr_lines[-20:])
                        )
                    err_detail += f"\n\nTRACEBACK:\n{worker_tb}"
                    hint = (
                        f"\n\n💡 Claude Agent SDK 自带 bundled CLI，"
                        f"无需单独安装 Node.js / Claude Code。"
                        f"\n当前工作目录: {resolved_cwd}"
                    )
                    yield f"⚠️ Claude Agent SDK 错误: {err_detail}{hint}"
                    return

                # kind == "msg"
                msg = payload
                logger.info(
                    f"[ClaudeSDK][{request_id}] raw response <- {self._serialize_sdk_message(msg)}"
                )
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            yield block.text
                        elif (
                            hasattr(block, "type")
                            and block.type == "tool_use"
                        ):
                            tool_name = getattr(
                                block, "name", "unknown"
                            )
                            if tool_collector is not None:
                                tool_collector.append(tool_name)
                            yield (
                                f"\n🔧 正在使用工具: {tool_name}..."
                            )
        else:
            # Normal path (Linux, macOS, etc.)
            try:
                logger.info(f"[ClaudeSDK][{request_id}] calling query()")
                async for msg in query(
                    prompt=_build_prompt_input(), options=options
                ):
                    logger.info(
                        f"[ClaudeSDK][{request_id}] raw response <- {self._serialize_sdk_message(msg)}"
                    )
                    if hasattr(msg, "content"):
                        for block in msg.content:
                            if hasattr(block, "text"):
                                yield block.text
                            elif (
                                hasattr(block, "type")
                                and block.type == "tool_use"
                            ):
                                tool_name = getattr(
                                    block, "name", "unknown"
                                )
                                if tool_collector is not None:
                                    tool_collector.append(tool_name)
                                yield (
                                    f"\n🔧 正在使用工具: {tool_name}..."
                                )
                logger.info(f"[ClaudeSDK][{request_id}] query() completed")
            except Exception as e:
                import traceback

                cause = e
                cause_chain = []
                while cause is not None:
                    cause_chain.append(
                        f"{type(cause).__name__}: {cause}"
                    )
                    cause = cause.__cause__
                    if len(cause_chain) > 5:
                        break
                logger.exception(f"[ClaudeSDK][{request_id}] failed: {e}")
                logger.error(
                    f"Cause chain: {' ← '.join(cause_chain)}"
                )
                err_detail = str(e)
                if stderr_lines:
                    err_detail += (
                        "\n\nSTDERR:\n"
                        + "\n".join(stderr_lines[-20:])
                    )
                tb = traceback.format_exc()
                err_detail += f"\n\nTRACEBACK:\n{tb}"
                hint = ""
                err_lower = (
                    str(e)
                    + "\n"
                    + "\n".join(cause_chain)
                    + "\n"
                    + "\n".join(stderr_lines)
                ).lower()
                if (
                    "failed to start" in err_lower
                    or "no such file" in err_lower
                    or "not found" in err_lower
                    or "notimplementederror" in err_lower
                ):
                    hint = (
                        f"\n\n💡 SDK 自带 bundled CLI，通常无需手动安装。"
                        f"\n如果仍失败，可手动安装："
                        f"npm install -g @anthropic-ai/claude-code"
                        f"\n工作目录: {resolved_cwd}"
                    )
                yield f"⚠️ Claude Agent SDK 错误: {err_detail}{hint}"

    def _build_agent_prompt(self, conversation: List[Dict[str, str]]) -> str:
        """Build a prompt from conversation history for the agent SDK."""
        if not conversation:
            return ""

        # For single message, just return it
        if len(conversation) == 1 and conversation[0]["role"] == "user":
            return conversation[0]["content"]

        # For multi-turn, format as a transcript
        lines = []
        for msg in conversation[-20:]:  # Last 20 messages
            role_label = "用户" if msg["role"] == "user" else "助手"
            content = msg["content"][:2000]  # Truncate long messages
            lines.append(f"{role_label}: {content}")

        return "\n".join(lines)

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