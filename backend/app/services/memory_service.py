import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, UserMemory
from app.schemas import MemoryCreate, MemoryUpdate


class MemoryService:
    """
    Long-term memory management per user.
    Stores preferences, facts, conversation summaries, habits.
    """
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def create_memory(self, data: MemoryCreate) -> UserMemory:
        memory = UserMemory(
            id=str(uuid.uuid4()),
            user_id=self.user.id,
            memory_type=data.memory_type,
            content=data.content,
            importance=data.importance,
        )
        self.db.add(memory)
        await self.db.flush()
        await self.db.refresh(memory)
        return memory

    async def get_memory(self, memory_id: str) -> Optional[UserMemory]:
        result = await self.db.execute(
            select(UserMemory).where(
                and_(UserMemory.id == memory_id, UserMemory.user_id == self.user.id)
            )
        )
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 50,
        skip: int = 0
    ) -> List[UserMemory]:
        query = select(UserMemory).where(UserMemory.user_id == self.user.id)
        if memory_type:
            query = query.where(UserMemory.memory_type == memory_type)
        query = query.order_by(UserMemory.importance.desc(), UserMemory.last_accessed.desc())
        result = await self.db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def get_relevant_memories(self, query: str, limit: int = 10) -> List[UserMemory]:
        """
        Get memories relevant to a query.
        Simple implementation: keyword match + importance score.
        Upgrade: use embedding + vector similarity.
        """
        memories = await self.list_memories(limit=limit * 2)
        
        if not query:
            return memories[:limit]
        
        # Simple relevance: count keyword overlaps
        query_words = set(query.lower().split())
        scored = []
        for m in memories:
            content_words = set(m.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append((overlap * m.importance, m))
        
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:limit]]

    async def update_memory(self, memory_id: str, data: MemoryUpdate) -> Optional[UserMemory]:
        memory = await self.get_memory(memory_id)
        if not memory:
            return None
        
        if data.content is not None:
            memory.content = data.content
        if data.importance is not None:
            memory.importance = data.importance
        
        memory.last_accessed = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(memory)
        return memory

    async def delete_memory(self, memory_id: str) -> bool:
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        await self.db.delete(memory)
        await self.db.flush()
        return True

    async def update_from_conversation(self, user_message: str, assistant_response: str) -> None:
        """
        Analyze conversation and update memory.
        Simple implementation: extract facts/preferences mentioned.
        Upgrade: use LLM to summarize and extract key info.
        """
        # Extract potential preferences or facts (simplified)
        # Real implementation would use NER or LLM extraction
        pass

    async def get_user_profile_summary(self) -> dict:
        """Get a summary of the user's profile from memories"""
        memories = await self.list_memories(limit=100)
        return {
            "total_memories": len(memories),
            "by_type": self._group_by_type(memories),
            "top_memories": [m.content for m in memories[:5] if m.importance >= 8]
        }

    def _group_by_type(self, memories: List[UserMemory]) -> dict:
        groups = {}
        for m in memories:
            groups.setdefault(m.memory_type, []).append(m.content)
        return groups
