"""
handlers/admin/orders.py
Order admin: pending deliveries + owner/superadmin full order history.
"""

import math

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.settings import settings
from database.models import Order, OrderStatus
from keyboards.keyboards import (
    AdminAllOrdersPageCD,
    AdminDeliverCD,
    AdminMessageUserCD,
    AdminOrderInfoCD,
    AdminOrdersPageCD,
    DoDeliverCD,
    admin_orders_page_kb,
    back_to_admin_kb,
)
from middlewares.role_filter import OrderAdminFilter, OwnerOrSuperFilter
from services.order_feed_service import sync_order_feed
from services.db_service import (
    get_delivery_ready_orders,
    get_all_orders_page,
    get_order,
    log_action,
    mark_delivered,
)
from states.states import ContactUserStates, DeliverOrderStates

router = Router()


def _status_label(status: OrderStatus) -> str:
    mapping = {
        OrderStatus.pending: "PENDING",
        OrderStatus.submitted: "SUBMITTED",
        OrderStatus.paid: "PAID",
        OrderStatus.delivered: "DELIVERED",
        OrderStatus.rejected: "REJECTED",
        OrderStatus.expired: "EXPIRED",
        OrderStatus.cancelled: "CANCELLED",
    }
    return mapping.get(status, str(status))


def _all_orders_kb(orders: list[Order], page: int, total: int):
    builder = InlineKeyboardBuilder()
    for order in orders:
        plan = (order.plan_name or "-")[:14]
        builder.button(
            text=f"#{order.order_id} | U:{order.user_id} | {plan}",
            callback_data=AdminOrderInfoCD(order_id=order.order_id, page=page).pack(),
        )
    builder.adjust(1)

    per_page = settings.ORDERS_PER_PAGE
    total_pages = max(1, math.ceil(total / per_page))
    nav = []
    if page > 0:
        nav.append(("Prev", AdminAllOrdersPageCD(page=page - 1).pack()))
    nav.append((f"{page + 1}/{total_pages}", "noop"))
    if (page + 1) * per_page < total:
        nav.append(("Next", AdminAllOrdersPageCD(page=page + 1).pack()))

    for text, data in nav:
        builder.button(text=text, callback_data=data)
    builder.adjust(1, len(nav), 1)
    builder.button(text="Admin Panel", callback_data="admin:panel")
    return builder.as_markup()


@router.callback_query(F.data == "admin:orders", OrderAdminFilter())
async def cb_orders_menu(callback: CallbackQuery):
    await _show_orders_page(callback, 0)


@router.callback_query(AdminOrdersPageCD.filter(), OrderAdminFilter())
async def cb_orders_page(callback: CallbackQuery, callback_data: AdminOrdersPageCD):
    await _show_orders_page(callback, callback_data.page)


async def _show_orders_page(callback: CallbackQuery, page: int):
    orders, total = await get_delivery_ready_orders(page)
    if not orders and page == 0:
        await callback.message.edit_text(
            "<b>Pending Deliveries</b>\n\nNo orders to deliver.",
            reply_markup=back_to_admin_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"<b>Pending Deliveries</b> ({total})\n\nSelect an order to deliver:",
        reply_markup=admin_orders_page_kb(orders, page, total),
    )
    await callback.answer()


@router.callback_query(AdminDeliverCD.filter(), OrderAdminFilter())
@router.callback_query(DoDeliverCD.filter(), OrderAdminFilter())
async def cb_do_deliver(callback: CallbackQuery, callback_data: AdminDeliverCD | DoDeliverCD, state: FSMContext):
    order_id = callback_data.order_id
    order = await get_order(order_id)
    if not order or order.status != OrderStatus.paid:
        await callback.answer("Order not available for delivery.", show_alert=True)
        return

    await state.set_state(DeliverOrderStates.waiting_product)
    await state.update_data(order_id=order_id, user_id=order.user_id)
    text = (
        f"<b>Deliver Order #{order_id}</b>\n\n"
        f"Product: {order.product_name}\n"
        f"Plan: {order.plan_name}\n\n"
    )
    if order.customer_requirements_response:
        text += (
            "<b>User Details:</b>\n"
            f"{order.customer_requirements_response}\n\n"
        )
    text += "Send the product now (text/file/link)."
    await callback.message.answer(text)
    await callback.answer()


@router.message(DeliverOrderStates.waiting_product, OrderAdminFilter())
async def handle_deliver_product(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]
    user_id = data["user_id"]

    order = await get_order(order_id)
    if not order:
        await state.clear()
        return

    delivered = False
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "<b>Your Order is Ready</b>\n\n"
                f"Order: <b>#{order_id}</b>\n"
                f"Product: {order.product_name}\n\n"
                "<b>Your product details:</b>"
            ),
        )
        await message.copy_to(chat_id=user_id)
        delivered = True
    except Exception:
        delivered = False

    if delivered:
        await mark_delivered(order_id, message.from_user.id)
        await log_action(message.from_user.id, "deliver_order", order_id)
        await sync_order_feed(bot, order_id)
        await message.answer(
            f"<b>Delivered</b>\n\nOrder #{order_id} delivered to user.",
            reply_markup=back_to_admin_kb(),
        )
    else:
        await message.answer(
            f"Could not deliver to user.\nOrder #{order_id} status not updated.",
            reply_markup=back_to_admin_kb(),
        )
    await state.clear()


@router.callback_query(F.data == "admin:all_orders", OwnerOrSuperFilter())
async def cb_all_orders_menu(callback: CallbackQuery):
    await _show_all_orders_page(callback, 0)


@router.callback_query(AdminAllOrdersPageCD.filter(), OwnerOrSuperFilter())
async def cb_all_orders_page(callback: CallbackQuery, callback_data: AdminAllOrdersPageCD):
    await _show_all_orders_page(callback, callback_data.page)


async def _show_all_orders_page(callback: CallbackQuery, page: int):
    orders, total = await get_all_orders_page(page)
    if not orders and page == 0:
        await callback.message.edit_text(
            "<b>All Orders History</b>\n\nNo orders found.",
            reply_markup=back_to_admin_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"<b>All Orders History</b> ({total})\n\nOpen any order for details:",
        reply_markup=_all_orders_kb(orders, page, total),
    )
    await callback.answer()


@router.callback_query(AdminOrderInfoCD.filter(), OwnerOrSuperFilter())
async def cb_all_order_info(callback: CallbackQuery, callback_data: AdminOrderInfoCD):
    order = await get_order(callback_data.order_id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    created = order.created_at.strftime("%d %b %Y %H:%M") if order.created_at else "-"
    paid_at = order.paid_at.strftime("%d %b %Y %H:%M") if order.paid_at else "-"
    delivered_at = order.delivered_at.strftime("%d %b %Y %H:%M") if order.delivered_at else "-"
    username = order.user.username if order.user and order.user.username else "-"

    text = (
        f"<b>Order #{order.order_id}</b>\n\n"
        f"Status: <b>{_status_label(order.status)}</b>\n"
        f"User ID: <code>{order.user_id}</code>\n"
        f"Username: @{username}\n"
        f"Product: {order.product_name}\n"
        f"Plan: {order.plan_name}\n"
        f"Amount: <b>Rs {order.amount:.0f}</b>\n"
        f"UPI: <code>{order.upi_id}</code>\n"
        f"Created: {created}\n"
        f"Paid: {paid_at}\n"
        f"Delivered: {delivered_at}"
    )
    if order.requirements_text_snapshot:
        text += (
            f"\n\n<b>Required Info Prompt:</b>\n"
            f"{order.requirements_text_snapshot}"
        )
    if order.customer_requirements_response:
        text += (
            f"\n\n<b>User Submitted Details:</b>\n"
            f"{order.customer_requirements_response}"
        )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Message User",
        callback_data=AdminMessageUserCD(order_id=order.order_id, page=callback_data.page).pack(),
    )
    builder.button(
        text="Back to All Orders",
        callback_data=AdminAllOrdersPageCD(page=callback_data.page).pack(),
    )
    builder.button(text="Admin Panel", callback_data="admin:panel")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(AdminMessageUserCD.filter(), OwnerOrSuperFilter())
async def cb_message_user(callback: CallbackQuery, callback_data: AdminMessageUserCD, state: FSMContext):
    order = await get_order(callback_data.order_id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    await state.set_state(ContactUserStates.waiting_message)
    await state.update_data(
        contact_user_id=order.user_id,
        contact_order_id=order.order_id,
        contact_page=callback_data.page,
    )
    await callback.message.answer(
        f"<b>Message User</b>\n\n"
        f"Order: <b>#{order.order_id}</b>\n"
        f"User ID: <code>{order.user_id}</code>\n\n"
        "Ab jo bhi message/file/photo bhejoge, user ko forward ho jayega.",
    )
    await callback.answer()


@router.message(ContactUserStates.waiting_message, OwnerOrSuperFilter())
async def handle_message_user(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data.get("contact_user_id")
    order_id = data.get("contact_order_id")
    page = int(data.get("contact_page", 0))

    if not user_id or not order_id:
        await state.clear()
        await message.answer("Session expired. Please open order details again.")
        return

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "<b>Support Update</b>\n\n"
                f"Order: <b>#{order_id}</b>"
            ),
        )
        await message.copy_to(chat_id=user_id)
        await log_action(message.from_user.id, "message_user", order_id)
    except Exception:
        await state.clear()
        await message.answer("User ko message nahi gaya. User ne bot block kiya ho sakta hai.")
        return

    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Back to Order",
        callback_data=AdminOrderInfoCD(order_id=order_id, page=page).pack(),
    )
    builder.button(
        text="Back to All Orders",
        callback_data=AdminAllOrdersPageCD(page=page).pack(),
    )
    builder.button(text="Admin Panel", callback_data="admin:panel")
    builder.adjust(1)
    await message.answer("Message user ko successfully bhej diya.", reply_markup=builder.as_markup())
