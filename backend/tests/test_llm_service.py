"""
Tests for llm_service
"""
import pytest
from app.services.chat_service import ChatService
from app.services.llm_service import LLMService, LLMProviderService
from app.services.skill_catalog import get_agent_skill_names
from app.schemas import LLMProviderCreate


@pytest.mark.asyncio
async def test_provider_create(db_session):
    """Test creating an LLM provider"""
    svc = LLMProviderService(db_session)
    provider = await svc.create({
        "name": "Test Anthropic",
        "provider_type": "anthropic",
        "base_url": "https://api.test.com",
        "api_key": "test-key",
        "is_default": True,
        "models": {"default": "test-model"},
        "config": {"timeout": 30},
    })
    
    assert provider.id is not None
    assert provider.name == "Test Anthropic"
    assert provider.provider_type == "anthropic"
    assert provider.is_default is True


@pytest.mark.asyncio
async def test_provider_list(db_session, test_provider):
    """Test listing providers"""
    svc = LLMProviderService(db_session)
    providers = await svc.list()
    
    assert len(providers) >= 1
    assert providers[0].name == "Test Provider"


@pytest.mark.asyncio
async def test_provider_get(db_session, test_provider):
    """Test getting a provider by ID"""
    svc = LLMProviderService(db_session)
    provider = await svc.get(test_provider.id)
    
    assert provider is not None
    assert provider.id == test_provider.id


@pytest.mark.asyncio
async def test_provider_update(db_session, test_provider):
    """Test updating a provider"""
    svc = LLMProviderService(db_session)
    updated = await svc.update(test_provider.id, {
        "name": "Updated Name",
        "models": {"default": "new-model"},
    })
    
    assert updated.name == "Updated Name"
    assert updated.models["default"] == "new-model"


@pytest.mark.asyncio
async def test_provider_update_preserves_api_key_when_blank(db_session, test_provider):
    """Blank api_key in update payload should not overwrite the stored key."""
    svc = LLMProviderService(db_session)
    original_key = test_provider.api_key

    updated = await svc.update(test_provider.id, {
        "api_key": "   ",
        "name": "Still Has Key",
    })

    assert updated.name == "Still Has Key"
    assert updated.api_key == original_key


@pytest.mark.asyncio
async def test_provider_delete(db_session, test_provider):
    """Test deleting a provider"""
    svc = LLMProviderService(db_session)
    result = await svc.delete(test_provider.id)
    
    assert result is True
    
    # Verify deleted
    provider = await svc.get(test_provider.id)
    assert provider is None


@pytest.mark.asyncio
async def test_llm_service_get_default_provider(db_session, test_provider):
    """Test that LLM service picks up default provider"""
    svc = LLMService(db_session)
    provider = await svc._get_default_provider()
    
    assert provider is not None
    assert provider.is_default is True


@pytest.mark.asyncio
async def test_llm_service_get_model_name(db_session, test_provider):
    """Test model name retrieval by type"""
    svc = LLMService(db_session)
    
    assert svc._get_model_name(test_provider, "default") == "test-model"
    assert svc._get_model_name(test_provider, "opus") == "test-opus"
    assert svc._get_model_name(test_provider, "unknown") == "test-model"  # falls back to default


@pytest.mark.asyncio
async def test_llm_service_no_provider(db_session):
    """Test LLM service behavior when no provider is configured"""
    svc = LLMService(db_session)
    chunks = []
    async for chunk in svc.chat(messages=[{"role": "user", "content": "Hi"}], user_id="some-user"):
        chunks.append(chunk)
    
    response = "".join(chunks)
    assert "未配置" in response or "not found" in response.lower()


@pytest.mark.asyncio
async def test_claude_agent_third_party_provider_requires_api_key(db_session, test_provider):
    """Third-party claude_agent providers should fail fast when api_key is missing."""
    test_provider.provider_type = "claude_agent"
    test_provider.base_url = "https://api.minimax.chat/anthropic"
    test_provider.api_key = ""
    test_provider.models = {"default": "MiniMax-M2.7"}

    svc = LLMService(db_session)
    chunks = []
    async for chunk in svc.chat(
        messages=[{"role": "user", "content": "Hi"}],
        provider_id=test_provider.id,
        user_id="test-user-1",
    ):
        chunks.append(chunk)

    response = "".join(chunks)
    assert "未配置第三方渠道 API Key" in response


@pytest.mark.asyncio
async def test_dynamic_agent_skills_are_shared_between_prompt_and_allowlist(db_session, test_user, monkeypatch, tmp_path):
    """Dynamic skills should appear both in system prompt and Claude SDK skill allowlist."""
    skills_dir = tmp_path / ".claude" / "skills"
    skill_dir = skills_dir / "greet-yo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: greet-yo\n"
        "description: Responds with Hi xxx when user says Yo.\n"
        "---\n\n"
        "Respond to Yo with a friendly Hi {name}.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.services.skill_catalog.get_skills_dir", lambda: skills_dir)

    chat_svc = ChatService(db_session, test_user)
    system_prompt = await chat_svc._build_system_prompt("claude_agent")

    assert "### /greet-yo - Responds with Hi xxx when user says Yo." in system_prompt
    assert "greet-yo" in get_agent_skill_names()


def test_temporary_process_env_restores_original_values(db_session, monkeypatch):
    """Claude SDK auth env should be injected only for the duration of the call."""
    svc = LLMService(db_session)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "original-key")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    with svc._temporary_process_env({
        "ANTHROPIC_API_KEY": "temp-key",
        "ANTHROPIC_BASE_URL": "https://api.minimax.chat/anthropic",
    }):
        import os
        assert os.environ["ANTHROPIC_API_KEY"] == "temp-key"
        assert os.environ["ANTHROPIC_BASE_URL"] == "https://api.minimax.chat/anthropic"

    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "original-key"
    assert "ANTHROPIC_BASE_URL" not in os.environ
