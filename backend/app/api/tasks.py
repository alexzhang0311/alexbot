from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models import User
from app.schemas import ScheduledTaskCreate, ScheduledTaskUpdate, ScheduledTaskResponse
from app.services.auth_service import get_current_user
from app.services.task_scheduler import TaskSchedulerService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/scheduled", response_model=ScheduledTaskResponse)
async def create_scheduled_task(
    data: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = TaskSchedulerService(db, user)
    return await svc.create_task(data.model_dump())


@router.get("/scheduled", response_model=List[ScheduledTaskResponse])
async def list_scheduled_tasks(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = TaskSchedulerService(db, user)
    return await svc.list_tasks(include_inactive=include_inactive)


@router.get("/scheduled/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = TaskSchedulerService(db, user)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/scheduled/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: str,
    data: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = TaskSchedulerService(db, user)
    task = await svc.update_task(task_id, data.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/scheduled/{task_id}")
async def delete_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = TaskSchedulerService(db, user)
    deleted = await svc.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}
