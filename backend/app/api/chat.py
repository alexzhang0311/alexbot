import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, AsyncGenerator
from loguru import logger
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
    session = await chat_svc.create_session(
        title=data.title,
        model=data.model,
        provider_id=data.provider_id,
        tools_enabled=data.tools_enabled if data.tools_enabled is not None else True,
    )
    return _session_to_response(session)


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    sessions = await chat_svc.list_sessions(include_archived=include_archived)
    return [_session_to_response(s) for s in sessions]


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
    return _session_to_response(session)


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db, user)
    session = await chat_svc.update_session(session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)


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


# HTTP SSE removed - use WebSocket /api/chat/ws/{token} for streaming chat with user interaction


def _session_to_response(session: ChatSession) -> SessionResponse:
    """Convert ChatSession model to response, including new fields."""
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        model=session.model,
        provider_id=getattr(session, 'provider_id', None),
        tools_enabled=getattr(session, 'tools_enabled', True),
        is_pinned=session.is_pinned,
        is_archived=session.is_archived,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=getattr(session, '_message_count', 0),
    )
