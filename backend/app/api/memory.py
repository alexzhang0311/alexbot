from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models import User
from app.schemas import MemoryCreate, MemoryUpdate, MemoryResponse
from app.services.auth_service import get_current_user
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.post("/memories", response_model=MemoryResponse)
async def create_memory(
    data: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    return await svc.create_memory(data)


@router.get("/memories", response_model=List[MemoryResponse])
async def list_memories(
    memory_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    return await svc.list_memories(memory_type=memory_type, limit=limit, skip=skip)


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    memory = await svc.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.patch("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    data: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    memory = await svc.update_memory(memory_id, data)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    deleted = await svc.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted"}


@router.get("/profile/summary")
async def get_profile_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = MemoryService(db, user)
    return await svc.get_user_profile_summary()
