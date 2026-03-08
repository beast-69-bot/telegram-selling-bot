"""
database/connection.py
Async SQLAlchemy engine + session factory.
Works with SQLite (dev) and PostgreSQL (prod) - just change DATABASE_URL.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings
from database.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Create all tables and run lightweight compatibility fixes on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_bot_settings_columns(conn)

    await _seed_defaults()
    logger.info("Database initialized")


async def close_db() -> None:
    await engine.dispose()
    logger.info("Database connection closed")


async def _seed_defaults() -> None:
    """Insert owner admin and default BotSettings if they don't exist."""
    from sqlalchemy import select

    from database.models import Admin, AdminRole, BotSettings

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        current = result.scalar_one_or_none()
        if not current:
            session.add(
                BotSettings(
                    id=1,
                    upi_id=settings.UPI_ID,
                    upi_name=settings.UPI_NAME,
                    payment_gateway=settings.PAYMENT_GATEWAY,
                    xwallet_api_key=settings.XWALLET_API_KEY,
                )
            )
        else:
            if not current.payment_gateway:
                current.payment_gateway = settings.PAYMENT_GATEWAY
            if not current.xwallet_api_key:
                current.xwallet_api_key = settings.XWALLET_API_KEY

        result = await session.execute(select(Admin).where(Admin.id == settings.OWNER_ID))
        if not result.scalar_one_or_none():
            session.add(
                Admin(
                    id=settings.OWNER_ID,
                    username="owner",
                    role=AdminRole.owner,
                    added_by=None,
                )
            )

        await session.commit()


async def _ensure_bot_settings_columns(conn) -> None:
    """Add new BotSettings columns for older deployments without migrations."""
    if "sqlite" in settings.DATABASE_URL:
        result = await conn.execute(text("PRAGMA table_info(bot_settings)"))
        columns = {row[1] for row in result.fetchall()}
        if "payment_gateway" not in columns:
            await conn.execute(
                text("ALTER TABLE bot_settings ADD COLUMN payment_gateway VARCHAR(16) DEFAULT 'manual'")
            )
        if "xwallet_api_key" not in columns:
            await conn.execute(
                text("ALTER TABLE bot_settings ADD COLUMN xwallet_api_key VARCHAR(255) DEFAULT ''")
            )
        return

    await conn.execute(
        text(
            "ALTER TABLE bot_settings "
            "ADD COLUMN IF NOT EXISTS payment_gateway VARCHAR(16) DEFAULT 'manual'"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE bot_settings "
            "ADD COLUMN IF NOT EXISTS xwallet_api_key VARCHAR(255) DEFAULT ''"
        )
    )


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
