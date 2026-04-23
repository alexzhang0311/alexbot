from typing import List, Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timezone
import uuid
from sqlalchemy import select, update, and_
from app.models import User, ScheduledTask
from app.core.database import AsyncSession


class TaskSchedulerService:
    """
    Manages scheduled tasks: reminders, recurring jobs, one-time tasks.
    """
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self._scheduler = AsyncIOScheduler()
        self._task_map: Dict[str, ScheduledTask] = {}

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown()

    async def create_task(self, data: dict) -> ScheduledTask:
        """Create a new scheduled task"""
        task = ScheduledTask(
            id=str(uuid.uuid4()),
            user_id=self.user.id,
            name=data["name"],
            description=data.get("description"),
            task_type=data["task_type"],
            cron_expression=data.get("cron_expression"),
            payload=data["payload"],
            is_active=True,
        )
        
        # Calculate next run time
        if task.task_type == "recurring" and task.cron_expression:
            task.next_run = self._parse_cron_next(task.cron_expression)
        elif task.task_type == "one_time":
            task.next_run = datetime.fromisoformat(data["payload"].get("run_at"))
        
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        
        # Register with scheduler
        self._schedule_task(task)
        
        return task

    async def list_tasks(self, include_inactive: bool = False) -> List[ScheduledTask]:
        query = select(ScheduledTask).where(ScheduledTask.user_id == self.user.id)
        if not include_inactive:
            query = query.where(ScheduledTask.is_active == True)
        result = await self.db.execute(query.order_by(ScheduledTask.next_run))
        return list(result.scalars().all())

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        result = await self.db.execute(
            select(ScheduledTask).where(
                and_(ScheduledTask.id == task_id, ScheduledTask.user_id == self.user.id)
            )
        )
        return result.scalar_one_or_none()

    async def update_task(self, task_id: str, data: dict) -> Optional[ScheduledTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        
        if "name" in data:
            task.name = data["name"]
        if "description" in data:
            task.description = data["description"]
        if "is_active" in data:
            task.is_active = data["is_active"]
        if "cron_expression" in data:
            task.cron_expression = data["cron_expression"]
        if "payload" in data:
            task.payload = data["payload"]
        
        # Reschedule if needed
        if task.is_active and task.cron_expression:
            task.next_run = self._parse_cron_next(task.cron_expression)
            self._unschedule_task(task.id)
            self._schedule_task(task)
        
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        
        self._unschedule_task(task.id)
        await self.db.delete(task)
        await self.db.flush()
        return True

    def _schedule_task(self, task: ScheduledTask):
        """Register task with APScheduler"""
        if not task.is_active or not task.next_run:
            return
        
        job_id = f"{self.user.id}:{task.id}"
        
        if task.task_type == "recurring" and task.cron_expression:
            trigger = CronTrigger.from_crontab(task.cron_expression)
        else:
            trigger = DateTrigger(run_date=task.next_run)
        
        self._scheduler.add_job(
            self._execute_task_job,
            trigger,
            args=[task.id],
            id=job_id,
            replace_existing=True,
        )
        self._task_map[job_id] = task

    def _unschedule_task(self, task_id: str):
        job_id = f"{self.user.id}:{task_id}"
        self._scheduler.remove_job(job_id, jobstore=None)
        self._task_map.pop(job_id, None)

    async def _execute_task_job(self, task_id: str):
        """Execute a task job"""
        task = await self.get_task(task_id)
        if not task:
            return
        
        # Execute based on task type
        payload = task.payload
        if payload.get("type") == "reminder":
            # Send notification (via WebSocket, email, etc.)
            notification = payload.get("message", task.name)
            # TODO: dispatch notification
            print(f"[Reminder] User {self.user.id}: {notification}")
        
        # Update last run
        task.last_run = datetime.now(timezone.utc)
        if task.task_type == "recurring" and task.cron_expression:
            task.next_run = self._parse_cron_next(task.cron_expression)
        elif task.task_type == "one_time":
            task.is_active = False
        
        await self.db.flush()

    def _parse_cron_next(self, cron_expr: str) -> datetime:
        """Parse crontab expression and return next run time"""
        from croniter import croniter
        tz = timezone.utc
        cron = croniter(cron_expr, datetime.now(tz))
        return cron.get_next(datetime)
