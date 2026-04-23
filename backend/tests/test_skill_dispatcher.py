"""
Tests for skill_dispatcher
"""
import pytest
from app.services.skill_dispatcher import SkillDispatcher, Skill


class DummySkill(Skill):
    """A test skill that triggers on 'hello'"""
    name = "dummy"
    description = "A dummy skill for testing"
    trigger_keywords = ["hello", "hi"]
    
    async def execute(self, query, **kwargs):
        return f"Dummy executed: {query}"


@pytest.mark.asyncio
async def test_skill_dispatcher_register(db_session, test_user):
    """Test registering a skill"""
    dispatcher = SkillDispatcher(db_session, test_user)
    
    initial_count = len(dispatcher.list_skills())
    dispatcher.register(DummySkill)
    
    assert len(dispatcher.list_skills()) == initial_count + 1


@pytest.mark.asyncio
async def test_skill_dispatcher_unregister(db_session, test_user):
    """Test unregistering a skill"""
    dispatcher = SkillDispatcher(db_session, test_user)
    dispatcher.register(DummySkill)
    dispatcher.unregister("dummy")
    
    assert dispatcher.get_skill("dummy") is None


@pytest.mark.asyncio
async def test_skill_should_trigger(db_session, test_user):
    """Test skill trigger detection"""
    dispatcher = SkillDispatcher(db_session, test_user)
    skill = DummySkill(db_session, test_user)
    
    assert skill.should_trigger("Say hello to me") is True
    assert skill.should_trigger("Say hi there") is True
    assert skill.should_trigger("What's the weather") is False


@pytest.mark.asyncio
async def test_skill_dispatcher_check_and_execute(db_session, test_user):
    """Test automatic skill detection and execution"""
    dispatcher = SkillDispatcher(db_session, test_user)
    dispatcher.register(DummySkill)
    
    results = await dispatcher.check_and_execute("Say hello to me")
    
    assert "dummy" in results
    assert "Dummy executed" in results["dummy"]


@pytest.mark.asyncio
async def test_skill_dispatcher_no_trigger(db_session, test_user):
    """Test when no skill is triggered"""
    dispatcher = SkillDispatcher(db_session, test_user)
    dispatcher.register(DummySkill)
    
    # Test with a query that explicitly should NOT match any skill
    # (English geography question - none of our skills match this)
    results = await dispatcher.check_and_execute("Tell me about quantum physics")
    # QA skill has empty string as result when no match, so check results are empty or all empty
    assert len([k for k,v in results.items() if v]) == 0


@pytest.mark.asyncio
async def test_skill_dispatcher_execute_specific(db_session, test_user):
    """Test executing a specific skill by name"""
    dispatcher = SkillDispatcher(db_session, test_user)
    dispatcher.register(DummySkill)
    
    result = await dispatcher.execute_skill("dummy", "hello world")
    
    assert "Dummy executed" in result


@pytest.mark.asyncio
async def test_skill_dispatcher_execute_unknown_raises(db_session, test_user):
    """Test that executing unknown skill raises error"""
    dispatcher = SkillDispatcher(db_session, test_user)
    
    with pytest.raises(ValueError, match="not found"):
        await dispatcher.execute_skill("nonexistent-skill", "test")
