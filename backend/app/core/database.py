from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from app.core.config import get_settings

settings = get_settings()

# ── Engine ──────────────────────────────────────────────────────────
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"echo": settings.ENVIRONMENT == "development"}
if not is_sqlite:
    _engine_kwargs["pool_pre_ping"] = True
else:
    # SQLite needs connect_args for check_same_thread
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# Enable WAL mode + foreign keys for SQLite (runs on every new connection)
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# ── Session ─────────────────────────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
