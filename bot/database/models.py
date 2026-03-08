"""
database/models.py
SQLAlchemy async ORM models — supports both SQLite (dev) and PostgreSQL (prod).
"""

from datetime import datetime
from typing import Optional
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class AdminRole(str, PyEnum):
    owner         = "owner"
    super_admin   = "super_admin"
    product_admin = "product_admin"
    payment_admin = "payment_admin"
    order_admin   = "order_admin"


class OrderStatus(str, PyEnum):
    pending   = "pending"
    submitted = "submitted"   # Screenshot sent
    paid      = "paid"        # Payment approved
    delivered = "delivered"   # Product sent
    rejected  = "rejected"    # Payment rejected
    expired   = "expired"     # Timed out
    cancelled = "cancelled"


# ── Tables ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(BigInteger, primary_key=True)   # Telegram user_id
    username      = Column(String(64), nullable=True)
    full_name     = Column(String(128), nullable=False)
    is_banned     = Column(Boolean, default=False)
    total_orders  = Column(Integer, default=0)
    total_spent   = Column(Float, default=0.0)
    created_at    = Column(DateTime, server_default=func.now())
    last_active   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    orders        = relationship("Order", back_populates="user", lazy="select")


class Admin(Base):
    __tablename__ = "admins"

    id         = Column(BigInteger, primary_key=True)   # Telegram user_id
    username   = Column(String(64), nullable=True)
    role       = Column(Enum(AdminRole), nullable=False)
    is_active  = Column(Boolean, default=True)
    added_by   = Column(BigInteger, nullable=True)
    added_at   = Column(DateTime, server_default=func.now())


class Product(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String(128), nullable=False)
    image_file_id = Column(String(256), nullable=True)   # Telegram file_id
    tagline      = Column(String(256), nullable=True)
    description  = Column(Text, nullable=True)
    category     = Column(String(64), default="General")
    is_active    = Column(Boolean, default=True)
    sort_order   = Column(Integer, default=0)
    total_sales  = Column(Integer, default=0)
    created_by   = Column(BigInteger, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    plans        = relationship("Plan", back_populates="product",
                                cascade="all, delete-orphan", lazy="select")


class Plan(Base):
    __tablename__ = "plans"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(128), nullable=False)
    price      = Column(Float, nullable=False)
    is_active  = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    product    = relationship("Product", back_populates="plans")
    orders     = relationship("Order", back_populates="plan", lazy="select")


class Order(Base):
    __tablename__ = "orders"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    order_id            = Column(String(16), unique=True, nullable=False)  # e.g. ORD1042
    user_id             = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    plan_id             = Column(Integer, ForeignKey("plans.id"), nullable=False)
    product_name        = Column(String(128), nullable=False)  # Denormalized snapshot
    plan_name           = Column(String(128), nullable=False)  # Denormalized snapshot
    amount              = Column(Float, nullable=False)
    upi_id              = Column(String(128), nullable=False)  # UPI at time of order
    status              = Column(Enum(OrderStatus), default=OrderStatus.pending)
    screenshot_file_id  = Column(String(256), nullable=True)
    verified_by         = Column(BigInteger, nullable=True)
    delivered_by        = Column(BigInteger, nullable=True)
    reject_reason       = Column(String(256), nullable=True)
    expires_at          = Column(DateTime, nullable=False)
    paid_at             = Column(DateTime, nullable=True)
    delivered_at        = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, server_default=func.now())

    user   = relationship("User", back_populates="orders")
    plan   = relationship("Plan", back_populates="orders")


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id                       = Column(Integer, primary_key=True, default=1)
    upi_id                   = Column(String(128), default="store@upi")
    upi_name                 = Column(String(128), default="My Store")
    payment_timeout_minutes  = Column(Integer, default=10)
    payment_gateway          = Column(String(16), default="manual")
    xwallet_api_key          = Column(String(255), default="")
    total_earnings           = Column(Float, default=0.0)
    welcome_message          = Column(Text, default="Welcome! Browse our products below.")
    maintenance_mode         = Column(Boolean, default=False)
    updated_at               = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    admin_id   = Column(BigInteger, nullable=False)
    action     = Column(String(64), nullable=False)
    target_id  = Column(String(64), nullable=True)
    details    = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
