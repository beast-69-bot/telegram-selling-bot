"""
handlers/admin/orders.py
Order admin: view paid orders, deliver products to users.
"""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.keyboards import (
    admin_orders_page_kb, back_to_admin_kb, confirm_deliver_kb,
    AdminOrdersPageCD, AdminDeliverCD, DoDeliverCD
)
from middlewares.role_filter import OrderAdminFilter
from services.db_service import get_order, get_orders_by_status, log_action, mark_delivered
from database.models import OrderStatus
from states.states import DeliverOrderStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin:orders", OrderAdminFilter())
async def cb_orders_menu(callback: CallbackQuery):
    await _show_orders_page(callback, 0)


@router.callback_query(AdminOrdersPageCD.filter(), OrderAdminFilter())
async def cb_orders_page(callback: CallbackQuery, callback_data: AdminOrdersPageCD):
    page = callback_data.page
    await _show_orders_page(callback, page)


async def _show_orders_page(callback: CallbackQuery, page: int):
    try:
        orders, total = await get_orders_by_status(OrderStatus.paid, page)
    except Exception as e:
        logger.error(f"Error fetching orders to deliver: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not orders and page == 0:
        await callback.message.edit_text(
            "📬 <b>Pending Deliveries</b>\n\n✅ No orders to deliver.",
            reply_markup=back_to_admin_kb(),
        )
        await callback.answer()
        return

    kb = admin_orders_page_kb(orders, page, total)
    await callback.message.edit_text(
        f"📬 <b>Pending Deliveries</b> ({total})\n\nSelect an order to deliver:",
        reply_markup=kb,
    )
    await callback.answer()


# ── Confirm Deliver Button (from payment approval notification) ───────────────

@router.callback_query(AdminDeliverCD.filter(), OrderAdminFilter())
@router.callback_query(DoDeliverCD.filter(), OrderAdminFilter())
async def cb_do_deliver(callback: CallbackQuery, callback_data: AdminDeliverCD | DoDeliverCD, state: FSMContext):
    # Both "admin_deliver:" (from order list) and "do_deliver:" (confirm button) lead here
    try:
        order_id = callback_data.order_id
        order = await get_order(order_id)
    except Exception as e:
        logger.error(f"Error checking order for delivery: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not order or order.status != OrderStatus.paid:
        await callback.answer("Order not available for delivery.", show_alert=True)
        return

    await state.set_state(DeliverOrderStates.waiting_product)
    await state.update_data(order_id=order_id, user_id=order.user_id)

    await callback.message.answer(
        f"📦 <b>Deliver Order #{order_id}</b>\n\n"
        f"Product: {order.product_name}\n"
        f"Plan: {order.plan_name}\n\n"
        f"<b>Send the product now</b> — text, credentials, file, or link.\n"
        f"Everything you send will be forwarded to the customer."
    )
    await callback.answer()


# ── Receive product from admin → forward to user ─────────────────────────────

@router.message(DeliverOrderStates.waiting_product, OrderAdminFilter())
async def handle_deliver_product(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]
    user_id  = data["user_id"]

    try:
        order = await get_order(order_id)
        if not order:
            await state.clear()
            return
    except Exception as e:
        logger.error(f"Error fetching order to complete delivery: {e}")
        await message.answer("⚠️ Something went wrong. Please try again or contact support.")
        return

    # Forward to user
    delivered = False
    try:
        header = (
            f"🎉 <b>Your Order is Ready!</b>\n\n"
            f"Order: <b>#{order_id}</b>\n"
            f"Product: {order.product_name}\n\n"
            f"<b>Your product details:</b>\n"
        )
        await bot.send_message(chat_id=user_id, text=header)

        # Forward the actual message (text, photo, document, etc.)
        await message.copy_to(chat_id=user_id)
        delivered = True
    except Exception as e:
        logger.error(f"Could not deliver to user {user_id}: {e}")

    if delivered:
        try:
            await mark_delivered(order_id, message.from_user.id)
            await log_action(message.from_user.id, "deliver_order", order_id)
        except Exception as e:
            logger.error(f"Error updating order state after delivery: {e}")
            await message.answer("⚠️ Order delivered but failed to update status in DB.")
            await state.clear()
            return

        await message.answer(
            f"✅ <b>Delivered!</b>\n\nOrder #{order_id} has been delivered to the customer.",
            reply_markup=back_to_admin_kb(),
        )
    else:
        await message.answer(
            f"⚠️ Could not deliver to user. They may have blocked the bot.\n"
            f"Order #{order_id} status not updated.",
            reply_markup=back_to_admin_kb(),
        )

    await state.clear()
