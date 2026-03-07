"""
database/connection.py
Async SQLAlchemy engine + session factory.
Works with SQLite (dev) and PostgreSQL (prod) — just change DATABASE_URL.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings
from database.models import Base

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # For SQLite only — not needed for PostgreSQL
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.DATABASE_URL
    else {},
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed owner and default settings
    await _seed_defaults()
    logger.info("✅ Database initialized")


async def close_db() -> None:
    await engine.dispose()
    logger.info("Database connection closed")


async def _seed_defaults() -> None:
    """Insert owner admin and default BotSettings if they don't exist."""
    from database.models import Admin, AdminRole, BotSettings
    from sqlalchemy import select

    async with AsyncSessionFactory() as session:
        # Default settings row (id=1)
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        if not result.scalar_one_or_none():
            session.add(BotSettings(id=1, upi_id=settings.UPI_ID, upi_name=settings.UPI_NAME))

        # Owner admin row
        result = await session.execute(select(Admin).where(Admin.id == settings.OWNER_ID))
        if not result.scalar_one_or_none():
            session.add(Admin(
                id=settings.OWNER_ID,
                username="owner",
                role=AdminRole.owner,
                added_by=None,
            ))

        await session.commit()


# ── Context Manager ───────────────────────────────────────────────────────────

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
