"""
keyboards/keyboards.py
All inline keyboard builders in one place.
"""

import math
from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

class BrowseProductsCD(CallbackData, prefix="browse_products"):
    page: int

class ProductCD(CallbackData, prefix="product"):
    id: int

class PlansCD(CallbackData, prefix="plans"):
    product_id: int

class SelectPlanCD(CallbackData, prefix="select_plan"):
    plan_id: int

class OrderConfirmCD(CallbackData, prefix="confirm_order"):
    plan_id: int

class UploadScreenshotCD(CallbackData, prefix="upload_screenshot"):
    order_id: str

class CancelOrderCD(CallbackData, prefix="cancel_order"):
    order_id: str

class OrderDetailCD(CallbackData, prefix="order_detail"):
    order_id: str

class AdminProductCD(CallbackData, prefix="admin_product"):
    id: int

class AdminEditProductCD(CallbackData, prefix="admin_edit_product"):
    id: int

class AdminAddPlanCD(CallbackData, prefix="admin_add_plan"):
    product_id: int

class AdminDeleteProductCD(CallbackData, prefix="admin_delete_product"):
    id: int

class ConfirmDeleteProductCD(CallbackData, prefix="confirm_delete_product"):
    id: int

class ApprovePaymentCD(CallbackData, prefix="approve_payment"):
    order_id: str

class RejectPaymentCD(CallbackData, prefix="reject_payment"):
    order_id: str

class ViewPaymentCD(CallbackData, prefix="view_payment"):
    order_id: str

class AdminOrdersPageCD(CallbackData, prefix="admin_orders_page"):
    page: int

class AdminAllOrdersPageCD(CallbackData, prefix="admin_all_orders_page"):
    page: int

class AdminDeliverCD(CallbackData, prefix="admin_deliver"):
    order_id: str

class DoDeliverCD(CallbackData, prefix="do_deliver"):
    order_id: str

class AdminOrderInfoCD(CallbackData, prefix="admin_order_info"):
    order_id: str
    page: int

class AdminMessageUserCD(CallbackData, prefix="admin_message_user"):
    order_id: str
    page: int

class AdminInfoCD(CallbackData, prefix="admin_info"):
    user_id: int

class RemoveAdminCD(CallbackData, prefix="remove_admin"):
    user_id: int

class SettingCD(CallbackData, prefix="setting"):
    key: str

class SetRoleCD(CallbackData, prefix="set_role"):
    role: str

class ToggleBanCD(CallbackData, prefix="toggle_ban"):
    user_id: int


from database.models import Order, Plan, Product
from config.settings import settings


# ═══════════════════════════════════════════════════════════════════════════════
# USER KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛍 Products", callback_data="browse_products:0")
    builder.button(text="👤 My Profile", callback_data="my_profile")
    builder.button(text="📦 My Orders", callback_data="my_orders")
    builder.button(text="💬 Support", callback_data="support")
    builder.adjust(2, 2)
    return builder.as_markup()


def products_page_kb(products: List[Product], page: int, total: int) -> InlineKeyboardMarkup:
    """Product listing with pagination."""
    builder = InlineKeyboardBuilder()

    for p in products:
        builder.button(
            text=f"{'🔴' if not p.is_active else '🟢'} {p.name}",
            callback_data=f"product:{p.id}",
        )

    builder.adjust(1)

    # Pagination row
    per_page = settings.PRODUCTS_PER_PAGE
    total_pages = math.ceil(total / per_page)
    nav_buttons = []

    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Prev", callback_data=f"browse_products:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop")
    )
    if (page + 1) * per_page < total:
        nav_buttons.append(
            InlineKeyboardButton(text="Next ▶️", callback_data=f"browse_products:{page + 1}")
        )

    builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardButton(text="🔍 Search", callback_data="search_products"),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
    )
    return builder.as_markup()


def product_detail_kb(product_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Select Plan", callback_data=f"plans:{product_id}")
    builder.button(text="◀️ Back to Products", callback_data=f"browse_products:{page}")
    builder.button(text="🏠 Main Menu", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def plans_kb(plans: List[Plan], product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=f"{plan.name} — ₹{plan.price:.0f}",
            callback_data=f"select_plan:{plan.id}",
        )
    builder.button(text="◀️ Back", callback_data=f"product:{product_id}")
    builder.adjust(1)
    return builder.as_markup()


def order_confirm_kb(plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm Order", callback_data=f"confirm_order:{plan_id}")
    builder.button(text="❌ Cancel", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


def payment_sent_kb(order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📸 I've sent payment", callback_data=f"upload_screenshot:{order_id}")
    builder.button(text="❌ Cancel Order", callback_data=f"cancel_order:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def cancel_screenshot_kb(order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data=f"cancel_order:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def my_orders_kb(orders: List[Order]) -> InlineKeyboardMarkup:
    from database.models import OrderStatus
    STATUS_EMOJI = {
        OrderStatus.pending:   "⏳",
        OrderStatus.submitted: "📤",
        OrderStatus.paid:      "✅",
        OrderStatus.delivered: "📦",
        OrderStatus.rejected:  "❌",
        OrderStatus.expired:   "🕐",
        OrderStatus.cancelled: "🚫",
    }
    builder = InlineKeyboardBuilder()
    for o in orders:
        emoji = STATUS_EMOJI.get(o.status, "❓")
        builder.button(
            text=f"{emoji} #{o.order_id} — {o.product_name[:20]}",
            callback_data=f"order_detail:{o.order_id}",
        )
    builder.button(text="🏠 Main Menu", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

def admin_panel_kb(show_all_orders: bool = False, show_revenue: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Products",   callback_data="admin:products")
    builder.button(text="💳 Payments",   callback_data="admin:payments")
    builder.button(text="📬 Orders",     callback_data="admin:orders")
    if show_all_orders:
        builder.button(text="📚 All Orders", callback_data="admin:all_orders")
    if show_revenue:
        builder.button(text="💰 Revenue", callback_data="admin:revenue")
    builder.button(text="👥 Admins",     callback_data="admin:admins")
    builder.button(text="⚙️ Settings",   callback_data="admin:settings")
    builder.button(text="📊 Stats",      callback_data="admin:stats")
    builder.button(text="📢 Broadcast",  callback_data="admin:broadcast")
    builder.button(text="🚫 Ban Users",  callback_data="admin:ban")
    builder.adjust(2, 2, 2, 2, 2)
    return builder.as_markup()


def admin_products_kb(products: List[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        status = "✅" if p.is_active else "❌"
        builder.button(text=f"{status} {p.name}", callback_data=AdminProductCD(id=p.id).pack())
    builder.button(text="➕ Add Product", callback_data="admin_add_product")
    builder.button(text="◀️ Back",        callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def admin_product_actions_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit",         callback_data=AdminEditProductCD(id=product_id).pack())
    builder.button(text="➕ Add Plan",     callback_data=AdminAddPlanCD(product_id=product_id).pack())
    builder.button(text="🗑 Delete",       callback_data=AdminDeleteProductCD(id=product_id).pack())
    builder.button(text="◀️ Back",        callback_data="admin:products")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def payment_verify_kb(order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=ApprovePaymentCD(order_id=order_id).pack())
    builder.button(text="❌ Reject",  callback_data=RejectPaymentCD(order_id=order_id).pack())
    builder.adjust(2)
    return builder.as_markup()


def admin_orders_page_kb(orders: List[Order], page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for o in orders:
        builder.button(
            text=f"#{o.order_id} — {o.product_name[:25]}",
            callback_data=AdminDeliverCD(order_id=o.order_id).pack(),
        )
    builder.adjust(1)

    per_page = settings.ORDERS_PER_PAGE
    total_pages = math.ceil(total / per_page) or 1
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=AdminOrdersPageCD(page=page-1).pack()))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=AdminOrdersPageCD(page=page+1).pack()))
    if nav:
        builder.row(*nav)

    builder.row(InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin:panel"))
    return builder.as_markup()


def confirm_deliver_kb(order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Deliver Now", callback_data=DoDeliverCD(order_id=order_id).pack())
    builder.button(text="◀️ Back",        callback_data="admin:orders")
    builder.adjust(1)
    return builder.as_markup()


def admin_roles_kb() -> InlineKeyboardMarkup:
    from database.models import AdminRole
    builder = InlineKeyboardBuilder()
    for role in [AdminRole.product_admin, AdminRole.payment_admin,
                 AdminRole.order_admin, AdminRole.super_admin]:
        builder.button(text=role.value.replace("_", " ").title(), callback_data=SetRoleCD(role=role.value).pack())
    builder.button(text="◀️ Cancel", callback_data="admin:admins")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def _admin_recent_users_kb_legacy(users: List["User"]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        status = "ðŸš«" if getattr(user, "is_banned", False) else "ðŸŸ¢"
        label = user.username or user.full_name or str(user.id)
        builder.button(
            text=f"{status} {label[:24]}",
            callback_data=ToggleBanCD(user_id=user.id).pack(),
        )
    builder.button(text="â—€ï¸ Admin Panel", callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def admin_recent_users_kb(users: List["User"]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        status = "[BANNED]" if getattr(user, "is_banned", False) else "[ACTIVE]"
        label = user.username or user.full_name or str(user.id)
        builder.button(
            text=f"{status} {label[:24]}",
            callback_data=ToggleBanCD(user_id=user.id).pack(),
        )
    builder.button(text="Back to Admin Panel", callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Admin Panel", callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Send to all users", callback_data="broadcast_confirm")
    builder.button(text="❌ Cancel",             callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()
