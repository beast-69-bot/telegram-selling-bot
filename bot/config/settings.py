"""
config/settings.py
All configuration loaded from environment variables via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # ── Bot ───────────────────────────────────────────────────────────────────
    BOT_TOKEN: str
    OWNER_ID: int

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./shopbot.db"
    # For PostgreSQL:
    # DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/shopbot"

    # ── Store ─────────────────────────────────────────────────────────────────
    UPI_ID: str = "store@upi"
    UPI_NAME: str = "My Store"
    STORE_NAME: str = "🛍 My Store"
    SUPPORT_USERNAME: str = "@support"
    XWALLET_API_KEY: str = ""
    PAYMENT_GATEWAY: str = "manual"  # "manual" or "xwallet"

    # ── Order Settings ────────────────────────────────────────────────────────
    ORDER_EXPIRY_MINUTES: int = 10
    MAX_PENDING_ORDERS: int = 3        # Max simultaneous pending orders per user

    # ── Pagination ────────────────────────────────────────────────────────────
    PRODUCTS_PER_PAGE: int = 5
    ORDERS_PER_PAGE: int = 8

    # ── Broadcast ─────────────────────────────────────────────────────────────
    BROADCAST_DELAY: float = 0.05     # Seconds between messages (avoid flood)

    LOG_LEVEL: str = "INFO"

    @field_validator("BOT_TOKEN")
    def validate_bot_token(cls, v: str) -> str:
        if not (v and ":" in v and v.split(":")[0].isdigit()):
            raise ValueError("BOT_TOKEN must start with digits and contain ':'")
        return v

    @field_validator("OWNER_ID")
    def validate_owner_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("OWNER_ID must be positive integer > 0")
        return v

    @field_validator("ORDER_EXPIRY_MINUTES")
    def validate_expiry(cls, v: int) -> int:
        if not (1 <= v <= 60):
            raise ValueError("ORDER_EXPIRY_MINUTES must be between 1 and 60")
        return v

    @field_validator("MAX_PENDING_ORDERS")
    def validate_max_pending(cls, v: int) -> int:
        if not (1 <= v <= 10):
            raise ValueError("MAX_PENDING_ORDERS must be between 1 and 10")
        return v

    @field_validator("DATABASE_URL")
    def validate_db_url(cls, v: str) -> str:
        if not (v.startswith("sqlite") or v.startswith("postgresql")):
            raise ValueError("DATABASE_URL must start with 'sqlite' or 'postgresql'")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

try:
    settings = Settings()
except Exception as e:
    print(f"Environment Validation Error: {e}")
    import sys
    sys.exit(1)
