from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models import User
from app.schemas import LLMProviderCreate, LLMProviderUpdate, LLMProviderResponse, ChatRequest
from app.services.auth_service import get_current_user
from app.services.llm_service import LLMProviderService

router = APIRouter(prefix="/api/llm", tags=["llm"])


def provider_to_dict(provider) -> dict:
    """Convert SQLAlchemy provider to dict with masked API key"""
    data = {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider.provider_type,
        "base_url": provider.base_url,
        "is_default": provider.is_default,
        "models": provider.models or {},
        "config": provider.config or {},
        "is_active": provider.is_active,
        "created_at": provider.created_at.isoformat() if provider.created_at else None,
    }
    if provider.api_key:
        data["api_key_masked"] = provider.api_key[:6] + "***" + provider.api_key[-4:]
        data["api_key"] = provider.api_key
    else:
        data["api_key_masked"] = None
        data["api_key"] = None
    return data


@router.get("/providers", response_model=List[dict])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = LLMProviderService(db)
    providers = await svc.list()
    return [provider_to_dict(p) for p in providers]


@router.post("/providers", response_model=dict)
async def create_provider(
    data: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = LLMProviderService(db)
    provider = await svc.create(data.model_dump())
    return provider_to_dict(provider)


@router.get("/providers/{provider_id}", response_model=dict)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = LLMProviderService(db)
    provider = await svc.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_to_dict(provider)


@router.patch("/providers/{provider_id}", response_model=dict)
async def update_provider(
    provider_id: str,
    data: LLMProviderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = LLMProviderService(db)
    provider = await svc.update(provider_id, data.model_dump(exclude_unset=True))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_to_dict(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    svc = LLMProviderService(db)
    deleted = await svc.delete(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "deleted"}


@router.post("/test")
async def test_provider(
    data: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Test LLM provider connection"""
    import httpx
    
    base_url = data.base_url
    provider_type = data.provider_type
    api_key = data.api_key
    model = data.models.get("default", "") if data.models else ""
    
    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            if provider_type in ("anthropic", "claude_agent"):
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {api_key}"

        test_messages = [{"role": "user", "content": "Hi"}]

        if provider_type in ("anthropic", "claude_agent"):
            response = await httpx.AsyncClient(timeout=30).post(
                f"{base_url.rstrip('/')}/v1/messages",
                headers=headers,
                json={"model": model or "claude-3-5-haiku", "messages": test_messages, "max_tokens": 10}
            )
        else:
            response = await httpx.AsyncClient(timeout=30).post(
                f"{base_url.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json={"model": model or "gpt-4o", "messages": test_messages, "max_tokens": 10}
            )
        
        if response.status_code == 200:
            return {"status": "success", "message": "连接成功"}
        else:
            return {"status": "error", "message": f"请求失败: {response.status_code} - {response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "message": f"连接异常: {str(e)}"}