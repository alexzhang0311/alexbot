from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import json
import asyncio
from app.core.database import async_session
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
    """WebSocket endpoint for streaming chat with interactive permission approval."""
    # Authenticate via token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)

    try:
        async with async_session() as db:
            from sqlalchemy import select

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                await websocket.close(code=4004, reason="User not found")
                return

            from app.services.chat_service import ChatService
            chat_svc = ChatService(db, user)

            # ── Dual-channel setup ──
            # recv_queue: normal chat requests from frontend
            recv_queue: asyncio.Queue = asyncio.Queue()
            # perm_response_queue: permission responses during active streaming
            perm_response_queue: asyncio.Queue | None = None

            async def recv_loop():
                """Background task: continuously receive and route messages."""
                nonlocal perm_response_queue
                try:
                    while True:
                        data = await websocket.receive_text()
                        msg = json.loads(data)
                        # Route permission responses directly to the waiting handler
                        if msg.get("type") == "permission_response" and perm_response_queue is not None:
                            await perm_response_queue.put(msg)
                        else:
                            await recv_queue.put(msg)
                except WebSocketDisconnect:
                    await recv_queue.put(None)

            recv_task = asyncio.create_task(recv_loop())

            # ── Main message loop ──
            while True:
                raw = await recv_queue.get()
                if raw is None:
                    break  # WebSocket disconnected

                data = raw
                if isinstance(data, str):
                    data = json.loads(data)

                chat_request = ChatRequest(
                    session_id=data["session_id"],
                    message=data["message"],
                    model=data.get("model"),
                    stream=True,
                    skill_names=data.get("skill_names"),
                )

                await websocket.send_json({
                    "type": "start",
                    "session_id": chat_request.session_id,
                })

                # Create permission queue for this request's can_use_tool callback
                permission_queue: asyncio.Queue = asyncio.Queue()

                full_response = ""

                async def _stream():
                    nonlocal full_response
                    async for chunk in chat_svc.chat(
                        chat_request, _perm_queue=permission_queue
                    ):
                        full_response += chunk
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk,
                        })

                stream_task = asyncio.create_task(_stream())

                # Wait for stream to complete, handling permission requests in between
                while not stream_task.done():
                    perm_get = asyncio.create_task(permission_queue.get())
                    done, pending = await asyncio.wait(
                        [stream_task, perm_get],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if stream_task in done:
                        perm_get.cancel()
                        break

                    if perm_get in done:
                        # can_use_tool sent a permission request
                        perm_req = perm_get.result()
                        future = perm_req.pop("_future", None)

                        # Set perm_response_queue so recv_loop routes responses here
                        perm_response_queue = asyncio.Queue()

                        # Send request to frontend (now JSON-safe)
                        await websocket.send_json(perm_req)

                        # Wait for user's response
                        resp = await perm_response_queue.get()
                        perm_response_queue = None

                        if future:
                            future.set_result(resp)

                await websocket.send_json({
                    "type": "end",
                    "content": full_response,
                })

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        manager.disconnect(user_id)
    finally:
        if 'recv_task' in locals():
            recv_task.cancel()
