from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Web Tool"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://aiuser:aipassword123@localhost:5432/aiwebtool"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # LLM
    DEFAULT_MODEL: str = "MiniMax-M2.7"
    OPENAI_API_KEY: str = ""
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
