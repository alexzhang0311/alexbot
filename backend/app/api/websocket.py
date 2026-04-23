from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import asyncio
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
            
            # Listen for messages
            while True:
                data = await websocket.receive_text()
                request_data = json.loads(data)
                
                chat_request = ChatRequest(
                    session_id=request_data["session_id"],
                    message=request_data["message"],
                    model=request_data.get("model"),
                    stream=True,
                    skill_names=request_data.get("skill_names"),
                )
                
                # Send streaming response
                await websocket.send_json({"type": "start", "session_id": chat_request.session_id})
                
                full_response = ""
                async for chunk in chat_svc.chat(chat_request):
                    full_response += chunk
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk,
                    })
                
                await websocket.send_json({
                    "type": "end",
                    "content": full_response,
                })
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        manager.disconnect(user_id)
