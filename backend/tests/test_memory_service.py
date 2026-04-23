"""
Tests for memory_service
"""
import pytest
from app.services.memory_service import MemoryService
from app.schemas import MemoryCreate, MemoryUpdate


@pytest.mark.asyncio
async def test_create_memory(db_session, test_user):
    """Test creating a memory"""
    svc = MemoryService(db_session, test_user)
    memory = await svc.create_memory(MemoryCreate(
        memory_type="preference",
        content="User prefers dark mode",
        importance=8,
    ))
    
    assert memory.id is not None
    assert memory.memory_type == "preference"
    assert memory.content == "User prefers dark mode"
    assert memory.importance == 8


@pytest.mark.asyncio
async def test_list_memories(db_session, test_user):
    """Test listing memories"""
    svc = MemoryService(db_session, test_user)
    
    await svc.create_memory(MemoryCreate(memory_type="preference", content="Pref 1", importance=5))
    await svc.create_memory(MemoryCreate(memory_type="fact", content="Fact 1", importance=7))
    
    # List all
    all_memories = await svc.list_memories()
    assert len(all_memories) >= 2
    
    # Filter by type
    prefs = await svc.list_memories(memory_type="preference")
    assert all(m.memory_type == "preference" for m in prefs)


@pytest.mark.asyncio
async def test_get_relevant_memories(db_session, test_user):
    """Test getting relevant memories by query"""
    svc = MemoryService(db_session, test_user)
    
    await svc.create_memory(MemoryCreate(memory_type="fact", content="User works at tech company", importance=7))
    await svc.create_memory(MemoryCreate(memory_type="preference", content="User likes Python", importance=6))
    await svc.create_memory(MemoryCreate(memory_type="habit", content="User drinks coffee in morning", importance=5))
    
    # Query for "Python"
    relevant = await svc.get_relevant_memories("Python programming language")
    assert len(relevant) > 0
    assert any("Python" in m.content for m in relevant)


@pytest.mark.asyncio
async def test_update_memory(db_session, test_user):
    """Test updating a memory"""
    svc = MemoryService(db_session, test_user)
    memory = await svc.create_memory(MemoryCreate(
        memory_type="preference",
        content="Old content",
        importance=5,
    ))
    
    updated = await svc.update_memory(memory.id, MemoryUpdate(
        content="Updated content",
        importance=9,
    ))
    
    assert updated.content == "Updated content"
    assert updated.importance == 9


@pytest.mark.asyncio
async def test_delete_memory(db_session, test_user):
    """Test deleting a memory"""
    svc = MemoryService(db_session, test_user)
    memory = await svc.create_memory(MemoryCreate(
        memory_type="temp",
        content="To be deleted",
    ))
    
    result = await svc.delete_memory(memory.id)
    assert result is True
    
    # Verify deleted
    fetched = await svc.get_memory(memory.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_get_user_profile_summary(db_session, test_user):
    """Test getting user profile summary"""
    svc = MemoryService(db_session, test_user)
    
    await svc.create_memory(MemoryCreate(memory_type="preference", content="Likes Python", importance=8))
    await svc.create_memory(MemoryCreate(memory_type="fact", content="Works at startup", importance=7))
    
    summary = await svc.get_user_profile_summary()
    
    assert summary["total_memories"] >= 2
    assert "preference" in summary["by_type"]
    assert "Likes Python" in summary["top_memories"]
