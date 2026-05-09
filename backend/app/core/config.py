from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Web Tool"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    # Database — production uses PostgreSQL; development uses SQLite
    DATABASE_URL: str = ""

    # Redis (optional, only used in production)
    REDIS_URL: str = ""

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # LLM
    DEFAULT_MODEL: str = "MiniMax-M2.7"
    OPENAI_API_KEY: str = ""

    def model_post_init(self, _context):
        """Auto-select database URL based on ENVIRONMENT if not explicitly set."""
        if not self.DATABASE_URL:
            if self.ENVIRONMENT == "production":
                self.DATABASE_URL = (
                    "postgresql+asyncpg://aiuser:aipassword123@postgres:5432/aiwebtool"
                )
            else:
                # SQLite for dev — file lives in backend/ directory
                db_path = PROJECT_ROOT / "dev.db"
                self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

        if not self.REDIS_URL:
            if self.ENVIRONMENT == "production":
                self.REDIS_URL = "redis://redis:6379/0"
            # dev: stays empty (no Redis needed)

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT != "production"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
