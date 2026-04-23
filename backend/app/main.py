from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth_router, chat_router, ws_router, memory_router, tasks_router, skills_router, llm_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created")
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


@app.get("/")
async def root():
    return {"message": "AI Web Tool API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
