"""
Tests for llm_service
"""
import pytest
from app.services.llm_service import LLMService, LLMProviderService
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
