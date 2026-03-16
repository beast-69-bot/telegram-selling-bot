"""
services/db_service.py
All database operations in one place — keeps handlers clean.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.settings import settings
from database.connection import get_session
from database.models import (
    Admin, AdminRole, AuditLog, BotSettings,
    Order, OrderStatus, Plan, Product, User,
)
from utils.order_id import generate_order_id

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# USER SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def upsert_user(user_id: int, username: Optional[str], full_name: str) -> User:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.username    = username
            user.full_name   = full_name
            user.last_active = datetime.now(timezone.utc)
        else:
            user = User(id=user_id, username=username, full_name=full_name)
            session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user(user_id: int) -> Optional[User]:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def get_all_users() -> List[User]:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.is_banned == False))
        return list(result.scalars().all())

async def get_recent_users(limit: int = 20) -> List[User]:
    async with get_session() as session:
        result = await session.execute(
            select(User).order_by(User.last_active.desc()).limit(limit)
        )
        return list(result.scalars().all())

async def toggle_user_ban(user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = not user.is_banned
            await session.commit()
            return user.is_banned
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def get_admin(user_id: int) -> Optional[Admin]:
    async with get_session() as session:
        result = await session.execute(
            select(Admin).where(Admin.id == user_id, Admin.is_active == True)
        )
        return result.scalar_one_or_none()


async def get_all_admins() -> List[Admin]:
    async with get_session() as session:
        result = await session.execute(select(Admin).where(Admin.is_active == True))
        return list(result.scalars().all())


async def add_admin(user_id: int, username: Optional[str], role: AdminRole, added_by: int) -> Admin:
    async with get_session() as session:
        admin = Admin(id=user_id, username=username, role=role, added_by=added_by)
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


async def remove_admin(user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(select(Admin).where(Admin.id == user_id))
        admin = result.scalar_one_or_none()
        if admin and admin.role != AdminRole.owner:
            admin.is_active = False
            await session.commit()
            return True
        return False


async def get_admins_by_role(*roles: AdminRole) -> List[Admin]:
    async with get_session() as session:
        result = await session.execute(
            select(Admin).where(Admin.role.in_(roles), Admin.is_active == True)
        )
        return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def get_products_page(page: int = 0) -> Tuple[List[Product], int]:
    """Returns (products_on_page, total_count)."""
    limit = settings.PRODUCTS_PER_PAGE
    async with get_session() as session:
        total_result = await session.execute(
            select(func.count(Product.id)).where(Product.is_active == True)
        )
        total = total_result.scalar_one()

        result = await session.execute(
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.sort_order, Product.id)
            .offset(page * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total


async def get_product(product_id: int) -> Optional[Product]:
    async with get_session() as session:
        result = await session.execute(
            select(Product)
            .options(selectinload(Product.plans))
            .where(Product.id == product_id, Product.is_active == True)
        )
        return result.scalar_one_or_none()


async def get_all_products() -> List[Product]:
    async with get_session() as session:
        result = await session.execute(
            select(Product)
            .options(selectinload(Product.plans))
            .where(Product.is_active == True)
            .order_by(Product.sort_order, Product.id)
        )
        return list(result.scalars().all())


async def search_products(query: str) -> List[Product]:
    async with get_session() as session:
        result = await session.execute(
            select(Product)
            .where(
                Product.is_active == True,
                (Product.name.ilike(f"%{query}%")) | (Product.description.ilike(f"%{query}%")) | (Product.tagline.ilike(f"%{query}%"))
            )
            .order_by(Product.sort_order, Product.id)
        )
        return list(result.scalars().all())


async def create_product(
    name: str,
    emoji: str,
    tagline: str,
    description: str,
    requirements_text: Optional[str],
    image_file_id: Optional[str],
    category: str,
    created_by: int,
) -> Product:
    async with get_session() as session:
        product = Product(
            name=name, emoji=emoji, tagline=tagline, description=description,
            requirements_text=requirements_text,
            image_file_id=image_file_id, category=category, created_by=created_by,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product


async def update_product(product_id: int, **kwargs) -> bool:
    async with get_session() as session:
        await session.execute(
            update(Product).where(Product.id == product_id).values(**kwargs)
        )
        await session.commit()
        return True


async def delete_product(product_id: int) -> bool:
    async with get_session() as session:
        await session.execute(
            update(Product).where(Product.id == product_id).values(is_active=False)
        )
        await session.commit()
        return True


async def add_plan(product_id: int, name: str, price: float) -> Plan:
    async with get_session() as session:
        plan = Plan(product_id=product_id, name=name, price=price)
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


async def get_plan(plan_id: int) -> Optional[Plan]:
    async with get_session() as session:
        result = await session.execute(
            select(Plan)
            .options(selectinload(Plan.product))
            .where(Plan.id == plan_id, Plan.is_active == True)
        )
        return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def count_pending_orders(user_id: int) -> int:
    async with get_session() as session:
        result = await session.execute(
            select(func.count(Order.id)).where(
                Order.user_id == user_id,
                Order.status == OrderStatus.pending,
            )
        )
        return result.scalar_one()


async def create_order(user_id: int, plan_id: int, upi_id: str) -> Order:
    plan = await get_plan(plan_id)
    if not plan:
        raise ValueError("Plan not found")

    timeout = await get_setting("payment_timeout_minutes") or settings.ORDER_EXPIRY_MINUTES

    requirements_text = (plan.product.requirements_text or "").strip()
    async with get_session() as session:
        order = Order(
            order_id     = generate_order_id(),
            user_id      = user_id,
            plan_id      = plan_id,
            product_name = plan.product.name,
            plan_name    = plan.name,
            amount       = plan.price,
            upi_id       = upi_id,
            requirements_text_snapshot=requirements_text or None,
            requirements_received=not bool(requirements_text),
            expires_at   = datetime.now(timezone.utc) + timedelta(minutes=int(timeout)),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def get_order(order_id: str) -> Optional[Order]:
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.plan))
            .where(Order.order_id == order_id)
        )
        return result.scalar_one_or_none()


async def get_order_by_id(pk: int) -> Optional[Order]:
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user))
            .where(Order.id == pk)
        )
        return result.scalar_one_or_none()


async def get_orders_by_status(
    status: OrderStatus, page: int = 0
) -> Tuple[List[Order], int]:
    limit = settings.ORDERS_PER_PAGE
    async with get_session() as session:
        total_result = await session.execute(
            select(func.count(Order.id)).where(Order.status == status)
        )
        total = total_result.scalar_one()

        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user))
            .where(Order.status == status)
            .order_by(Order.created_at.asc())
            .offset(page * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total


async def get_delivery_ready_orders(page: int = 0) -> Tuple[List[Order], int]:
    limit = settings.ORDERS_PER_PAGE
    async with get_session() as session:
        total_result = await session.execute(
            select(func.count(Order.id)).where(
                Order.status == OrderStatus.paid,
                Order.requirements_received == True,
            )
        )
        total = total_result.scalar_one()

        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.plan))
            .where(
                Order.status == OrderStatus.paid,
                Order.requirements_received == True,
            )
            .order_by(Order.created_at.asc())
            .offset(page * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total


async def get_all_orders_page(page: int = 0) -> Tuple[List[Order], int]:
    """Paginated orders history sorted by newest first."""
    limit = settings.ORDERS_PER_PAGE
    async with get_session() as session:
        total_result = await session.execute(select(func.count(Order.id)))
        total = total_result.scalar_one()

        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.plan))
            .order_by(Order.created_at.desc())
            .offset(page * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total


async def update_order_status(
    order_id: str,
    status: OrderStatus,
    **kwargs,
) -> bool:
    async with get_session() as session:
        values = {"status": status, **kwargs}
        await session.execute(
            update(Order).where(Order.order_id == order_id).values(**values)
        )
        await session.commit()
        return True


async def submit_screenshot(order_id: str, file_id: str) -> bool:
    return await update_order_status(
        order_id, OrderStatus.submitted, screenshot_file_id=file_id
    )


async def approve_payment(order_id: str, admin_id: int) -> bool:
    return await update_order_status(
        order_id, OrderStatus.paid,
        verified_by=admin_id,
        paid_at=datetime.now(timezone.utc),
    )


async def reject_payment(order_id: str, admin_id: int, reason: str) -> bool:
    return await update_order_status(
        order_id, OrderStatus.rejected,
        verified_by=admin_id,
        reject_reason=reason,
    )


async def mark_delivered(order_id: str, admin_id: int) -> bool:
    order = await get_order(order_id)
    if not order or order.status != OrderStatus.paid:
        return False

    result = await update_order_status(
        order_id,
        OrderStatus.delivered,
        delivered_by=admin_id,
        delivered_at=datetime.now(timezone.utc),
    )
    if not result:
        return False

    async with get_session() as session:
        await session.execute(
            update(Product)
            .where(Product.id == order.plan.product_id)
            .values(total_sales=Product.total_sales + 1)
        )
        await session.execute(
            update(User)
            .where(User.id == order.user_id)
            .values(
                total_orders=User.total_orders + 1,
                total_spent=User.total_spent + order.amount,
            )
        )
        await session.execute(
            update(BotSettings)
            .where(BotSettings.id == 1)
            .values(total_earnings=BotSettings.total_earnings + order.amount)
        )
        await session.commit()
    return True


async def save_customer_requirements(order_id: str, response: str) -> bool:
    return await update_order_status(
        order_id,
        OrderStatus.paid,
        customer_requirements_response=response,
        requirements_received=True,
    )


async def set_order_channel_message_id(order_id: str, message_id: int | None) -> bool:
    async with get_session() as session:
        await session.execute(
            update(Order).where(Order.order_id == order_id).values(channel_message_id=message_id)
        )
        await session.commit()
        return True


async def get_pending_requirements_order_for_user(user_id: int) -> Optional[Order]:
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.plan))
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatus.paid,
                Order.requirements_received == False,
            )
            .order_by(Order.paid_at.desc(), Order.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def expire_old_orders() -> List[Order]:
    """Called by scheduler — expire pending orders past their deadline."""
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.user))
            .where(Order.status == OrderStatus.pending, Order.expires_at <= now)
        )
        orders = list(result.scalars().all())
        if orders:
            ids = [o.order_id for o in orders]
            await session.execute(
                update(Order)
                .where(Order.order_id.in_(ids))
                .values(status=OrderStatus.expired)
            )
            await session.commit()
        return orders


async def get_user_orders(user_id: int) -> List[Order]:
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(10)
        )
        return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def get_settings() -> BotSettings:
    async with get_session() as session:
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        return result.scalar_one()


async def get_setting(key: str):
    s = await get_settings()
    return getattr(s, key, None)


async def update_setting(key: str, value) -> bool:
    async with get_session() as session:
        await session.execute(
            update(BotSettings).where(BotSettings.id == 1).values(**{key: value})
        )
        await session.commit()
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def log_action(admin_id: int, action: str, target_id: str = None, details: str = None):
    async with get_session() as session:
        session.add(AuditLog(
            admin_id=admin_id, action=action,
            target_id=str(target_id) if target_id else None,
            details=details,
        ))
        await session.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# STATS SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

async def get_stats() -> dict:
    async with get_session() as session:
        total_users    = (await session.execute(select(func.count(User.id)))).scalar_one()
        total_orders   = (await session.execute(select(func.count(Order.id)))).scalar_one()
        paid_orders    = (await session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.paid)
        )).scalar_one()
        delivered      = (await session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.delivered)
        )).scalar_one()
        total_revenue  = (await session.execute(
            select(func.sum(Order.amount)).where(
                Order.status.in_([OrderStatus.paid, OrderStatus.delivered])
            )
        )).scalar_one() or 0.0
        pending_verify = (await session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.submitted)
        )).scalar_one()

    return {
        "total_users":    total_users,
        "total_orders":   total_orders,
        "paid_orders":    paid_orders,
        "delivered":      delivered,
        "total_revenue":  total_revenue,
        "pending_verify": pending_verify,
    }


async def get_revenue_stats() -> dict:
    """Owner/superadmin revenue dashboard numbers."""
    async with get_session() as session:
        settings_row = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        bot_settings = settings_row.scalar_one()
        total_earnings = float(bot_settings.total_earnings or 0.0)

        delivered_orders = (
            await session.execute(select(func.count(Order.id)).where(Order.status == OrderStatus.delivered))
        ).scalar_one()

        pending_paid_amount = (
            await session.execute(select(func.sum(Order.amount)).where(Order.status == OrderStatus.paid))
        ).scalar_one() or 0.0

    avg_per_delivered = (total_earnings / delivered_orders) if delivered_orders else 0.0
    return {
        "total_earnings": total_earnings,
        "delivered_orders": delivered_orders,
        "pending_paid_amount": float(pending_paid_amount),
        "avg_per_delivered": float(avg_per_delivered),
    }
