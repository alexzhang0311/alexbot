from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import asyncio
import uuid
import concurrent.futures
import threading
from loguru import logger
from app.core.database import get_db, async_session
from app.models import User
from app.schemas import ChatRequest
from app.core.security import decode_token

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per user"""
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_message(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)


manager = ConnectionManager()


@router.websocket("/api/chat/ws/{token}")
async def websocket_chat(websocket: WebSocket, token: str):
    """WebSocket endpoint for streaming chat"""
    # Authenticate via token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    logger.info(f"[WS] connect user_id={user_id}")
    
    await manager.connect(websocket, user_id)
    
    try:
        # Get user from DB
        async with async_session() as db:
            from sqlalchemy import select
            from app.models import User
            
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user:
                await websocket.close(code=4004, reason="User not found")
                return
            
            from app.services.chat_service import ChatService
            chat_svc = ChatService(db, user)
            main_loop = asyncio.get_running_loop()
            send_lock = asyncio.Lock()
            pending_user_inputs: dict[str, concurrent.futures.Future] = {}
            pending_user_inputs_lock = threading.Lock()
            active_chat_task: Optional[asyncio.Task] = None

            async def send_json_safe(message: dict):
                async with send_lock:
                    await websocket.send_json(message)

            async def handle_user_input(tool_name: str, input_data: dict, context) -> dict:
                """Bridge Claude SDK can_use_tool callback to frontend interaction."""
                request_id = str(uuid.uuid4())[:8]
                prompt_kind = "question" if tool_name == "AskUserQuestion" else "approval"
                response_future: concurrent.futures.Future = concurrent.futures.Future()

                logger.info(
                    f"[WS][USER_INPUT] 🔔 Agent 请求用户响应 user_id={user_id} "
                    f"request_id={request_id} kind={prompt_kind} tool={tool_name}"
                )
                if prompt_kind == "approval":
                    logger.info(f"[WS][USER_INPUT][APPROVAL] 工具参数: {json.dumps(input_data, ensure_ascii=False)[:500]}")
                elif prompt_kind == "question" and input_data.get("questions"):
                    logger.info(
                        f"[WS][USER_INPUT][QUESTION] 问题数: {len(input_data.get('questions', []))} "
                        f"首个问题: {input_data['questions'][0].get('question', '')[:100] if input_data.get('questions') else 'N/A'}"
                    )

                with pending_user_inputs_lock:
                    pending_user_inputs[request_id] = response_future

                try:
                    prompt_message = {
                        "type": "user_input_required",
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "kind": prompt_kind,
                        "input": input_data,
                    }
                    current_loop = asyncio.get_running_loop()
                    if current_loop is main_loop:
                        await send_json_safe(prompt_message)
                    else:
                        await asyncio.wrap_future(
                            asyncio.run_coroutine_threadsafe(
                                send_json_safe(prompt_message),
                                main_loop,
                            )
                        )

                    payload = await asyncio.wrap_future(response_future)
                finally:
                    with pending_user_inputs_lock:
                        pending_user_inputs.pop(request_id, None)

                behavior = str(payload.get("behavior", "")).lower()
                if not behavior:
                    if payload.get("allow") is True:
                        behavior = "allow"
                    elif payload.get("allow") is False:
                        behavior = "deny"
                    else:
                        behavior = "allow"

                if behavior == "deny":
                    deny_msg = payload.get("message") or "User denied this action"
                    logger.info(
                        f"[WS][USER_INPUT] ❌ 用户拒绝 user_id={user_id} "
                        f"request_id={request_id} tool={tool_name} reason={deny_msg}"
                    )
                    return {
                        "behavior": "deny",
                        "message": deny_msg,
                    }

                updated_input = payload.get("updated_input")
                if updated_input is None:
                    updated_input = input_data
                
                logger.info(
                    f"[WS][USER_INPUT] ✅ 用户允许 user_id={user_id} "
                    f"request_id={request_id} tool={tool_name}"
                )
                if prompt_kind == "question" and updated_input.get("answers"):
                    logger.info(
                        f"[WS][USER_INPUT][ANSWER] 用户回答: {json.dumps(updated_input.get('answers', {}), ensure_ascii=False)[:500]}"
                    )
                
                return {
                    "behavior": "allow",
                    "updated_input": updated_input,
                }

            async def process_chat_message(request_data: dict):
                nonlocal active_chat_task

                try:
                    if request_data.get("type") == "chat":
                        request_data = request_data.get("payload", request_data)

                    chat_request = ChatRequest(
                        session_id=request_data["session_id"],
                        message=request_data["message"],
                        model=request_data.get("model"),
                        provider_id=request_data.get("provider_id"),
                        tools_enabled=request_data.get("tools_enabled"),
                        stream=True,
                        skill_names=request_data.get("skill_names"),
                    )

                    await send_json_safe({"type": "start", "session_id": chat_request.session_id})
                    logger.info(f"[WS] message received user_id={user_id} session_id={chat_request.session_id}")

                    full_response = ""
                    tool_calls = []

                    async for chunk in chat_svc.chat(
                        chat_request,
                        _tool_collector=tool_calls,
                        _user_input_handler=handle_user_input,
                    ):
                        full_response += chunk
                        await send_json_safe({
                            "type": "chunk",
                            "content": chunk,
                        })

                    await chat_svc.save_message(
                        session_id=chat_request.session_id,
                        role="user",
                        content=chat_request.message,
                        model=chat_request.model or "default",
                    )
                    await chat_svc.save_message(
                        session_id=chat_request.session_id,
                        role="assistant",
                        content=full_response,
                        model=chat_request.model or "default",
                        metadata_data={"tool_calls": tool_calls} if tool_calls else {},
                    )
                    await db.commit()

                    await send_json_safe({
                        "type": "end",
                        "content": full_response,
                        "tool_calls": tool_calls,
                    })
                    logger.info(
                        f"[WS] completed user_id={user_id} session_id={chat_request.session_id} response_chars={len(full_response)}"
                    )
                except Exception as e:
                    logger.exception(f"[WS] chat processing failed user_id={user_id}: {e}")
                    await send_json_safe({"type": "error", "message": str(e)})
                finally:
                    active_chat_task = None
            
            # Listen for messages
            while True:
                data = await websocket.receive_text()
                request_data = json.loads(data)

                if request_data.get("type") == "ping":
                    await send_json_safe({"type": "pong"})
                    continue

                if request_data.get("type") == "user_input_response":
                    request_id = request_data.get("request_id")
                    response_future = None
                    with pending_user_inputs_lock:
                        response_future = pending_user_inputs.get(request_id)

                    if not request_id or response_future is None:
                        await send_json_safe({
                            "type": "notice",
                            "message": "当前没有待确认请求",
                            "request_id": request_id,
                        })
                        continue

                    if response_future.done():
                        await send_json_safe({
                            "type": "notice",
                            "message": "该确认请求已处理",
                            "request_id": request_id,
                        })
                        continue

                    logger.info(
                        f"[WS][USER_INPUT] 收到前端响应 user_id={user_id} request_id={request_id} "
                        f"behavior={request_data.get('behavior') or request_data.get('allow')}"
                    )
                    response_future.set_result(request_data)
                    continue

                if request_data.get("type") == "chat":
                    if active_chat_task and not active_chat_task.done():
                        await send_json_safe({
                            "type": "notice",
                            "message": "当前已有进行中的请求，请等待完成后再发送新消息",
                        })
                        continue

                    active_chat_task = asyncio.create_task(process_chat_message(request_data))
                    continue

                await send_json_safe({
                    "type": "error",
                    "message": f"Unsupported message type: {request_data.get('type')}",
                })
                
    except WebSocketDisconnect:
        logger.info(f"[WS] disconnect user_id={user_id}")
        if 'active_chat_task' in locals() and active_chat_task and not active_chat_task.done():
            active_chat_task.cancel()
        if 'pending_user_inputs' in locals():
            with pending_user_inputs_lock:
                for future in pending_user_inputs.values():
                    if not future.done():
                        future.set_exception(ConnectionError("WebSocket disconnected"))
        manager.disconnect(user_id)
    except Exception as e:
        logger.exception(f"[WS] failed user_id={user_id}: {e}")
        if 'active_chat_task' in locals() and active_chat_task and not active_chat_task.done():
            active_chat_task.cancel()
        if 'pending_user_inputs' in locals():
            with pending_user_inputs_lock:
                for future in pending_user_inputs.values():
                    if not future.done():
                        future.set_exception(e)
        await send_json_safe({"type": "error", "message": str(e)})
        manager.disconnect(user_id)
