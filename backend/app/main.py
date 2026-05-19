import os
import sys
import asyncio

# Windows: Claude Agent SDK relies on subprocess support.
# On Windows, SelectorEventLoop does not implement subprocess APIs,
# so explicitly use ProactorEventLoopPolicy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine, Base, async_session
from app.api import auth_router, chat_router, ws_router, memory_router, tasks_router, skills_router, llm_router

settings = get_settings()


def _configure_logging() -> None:
    """Configure log sinks (console + rotating file)."""
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", settings.LOG_DIR))
    os.makedirs(log_dir, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        enqueue=True,
        backtrace=True,
        diagnose=settings.is_dev,
    )
    logger.add(
        os.path.join(log_dir, "app.log"),
        level=settings.log_level,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        enqueue=True,
        backtrace=True,
        diagnose=settings.is_dev,
        encoding="utf-8",
        serialize=settings.LOG_SERIALIZE,
    )
    logger.info(
        f"Logging configured: level={settings.log_level} dir={log_dir} rotation={settings.LOG_ROTATION} retention={settings.LOG_RETENTION}"
    )


_configure_logging()


async def _seed_default_provider():
    """Create a default LLM provider if none exist (dev mode only)."""
    import uuid
    import shutil
    import os as _os
    from app.models import LLMProvider

    async with async_session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM llm_providers")
        )
        count = result.scalar()
        if count > 0:
            return  # already has providers

        # Check if claude CLI is available (system PATH, not .CMD wrappers).
        # On Windows, npm global installs create wrapper .CMD scripts that don't
        # work with anyio.open_process. Prefer SDK's bundled claude.exe.
        # On Linux/macOS, a real binary in PATH is fine to store.
        import platform
        has_claude = False
        claude_path = None
        if platform.system() != "Windows":
            claude_path = shutil.which("claude")
            has_claude = claude_path is not None

        if has_claude and claude_path:
            config = {
                "timeout": 120,
                "cli_path": claude_path,
                "cwd": str(_os.getcwd()),
                "tools_enabled": True,
            }
            logger.info(f"Seeded default: Claude Agent (cli={claude_path})")
        else:
            # No system claude found (or on Windows) — seed claude_agent anyway.
            # SDK will use its bundled CLI at runtime (no separate install needed).
            config = {
                "timeout": 120,
                "cwd": str(_os.getcwd()),
                "tools_enabled": True,
            }
            logger.info("Seeded default: Claude Agent (SDK auto-detect bundled CLI)")

        provider = LLMProvider(
            id=str(uuid.uuid4()),
            name="Claude Agent (默认)",
            provider_type="claude_agent",
            base_url="https://api.minimax.chat/anthropic",
            api_key=settings.OPENAI_API_KEY or "",
            is_default=True,
            models={"default": "MiniMax-M2.7"},
            config=config,
        )

        session.add(provider)
        await session.commit()


async def _run_migrations(conn):
    """Add new columns if they don't exist (idempotent)."""
    migrations = [
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS provider_id VARCHAR(64)",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS tools_enabled BOOLEAN DEFAULT TRUE",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
            logger.info(f"Migration OK: {sql[:60]}...")
        except Exception as e:
            logger.warning(f"Migration skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting up in {settings.ENVIRONMENT} mode (DB: {settings.DATABASE_URL[:50]}...)")
    
    # Create tables (works for both SQLite and PostgreSQL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations only on PostgreSQL (SQLite handles column adds differently)
    if not settings.is_dev:
        async with engine.begin() as conn:
            await _run_migrations(conn)

    # Seed default LLM provider in dev mode
    if settings.is_dev:
        await _seed_default_provider()

    logger.info("Database tables ready")
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="AI Web Tool - Internal company AI assistant platform",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(ws_router)
app.include_router(memory_router)
app.include_router(tasks_router)
app.include_router(skills_router)
app.include_router(llm_router)

# ── Dev mode: serve frontend static files directly ─────────────────
if settings.is_dev:
    frontend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public")
    )
    if os.path.isdir(frontend_dir):
        # Mounted last → only catches paths that don't match API routes
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
        logger.info(f"Dev mode: serving frontend from {frontend_dir}")
    else:
        logger.warning(f"Dev mode: frontend dir not found at {frontend_dir}")
else:
    # Production root endpoint
    @app.get("/")
    async def root():
        return {"message": "AI Web Tool API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
