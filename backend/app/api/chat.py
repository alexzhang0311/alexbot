from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models import User, ChatSession, Message
from app.schemas import (
    SessionCreate, SessionUpdate, SessionResponse,
    MessageCreate, MessageResponse, ChatRequest
)
from app.services.auth_service import get_current_user
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    session = await chat_svc.create_session(title=data.title, model=data.model)
    return session


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    sessions = await chat_svc.list_sessions(include_archived=include_archived)
    return [
        SessionResponse(
            id=s.id,
            user_id=s.user_id,
            title=s.title,
            model=s.model,
            is_pinned=s.is_pinned,
            is_archived=s.is_archived,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=getattr(s, '_message_count', 0),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    session = await chat_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    session = await chat_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if data.title is not None:
        session.title = data.title
    if data.is_pinned is not None:
        session.is_pinned = data.is_pinned
    if data.is_archived is not None:
        session.is_archived = data.is_archived
    
    await db.flush()
    await db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    deleted = await chat_svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    session_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    messages = await chat_svc.get_session_messages(session_id, limit=limit)
    return messages


@router.post("/chat", response_model=MessageResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Non-streaming chat endpoint.
    For streaming, use WebSocket /api/chat/websocket
    """
    chat_svc = ChatService(db, user)
    
    full_response = ""
    async for chunk in chat_svc.chat(request):
        full_response += chunk
    
    # Get the saved message
    messages = await chat_svc.get_session_messages(request.session_id, limit=1)
    return messages[-1] if messages else None
