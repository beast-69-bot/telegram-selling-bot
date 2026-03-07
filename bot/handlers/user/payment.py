"""
handlers/user/payment.py
Order creation → UPI QR → Screenshot upload → Admin notification.
"""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from config.settings import settings
from keyboards.keyboards import (
    cancel_screenshot_kb, main_menu_kb, payment_sent_kb,
    OrderConfirmCD, UploadScreenshotCD, CancelOrderCD
)
from services.db_service import (
    approve_payment, count_pending_orders, create_order, get_order,
    get_admins_by_role, get_settings, submit_screenshot, update_order_status,
    log_action,
)
from database.models import AdminRole, OrderStatus
from states.states import PaymentStates
from utils.qr_generator import generate_upi_qr

logger = logging.getLogger(__name__)
router = Router()


# ── Confirm Order → Create + Show Payment QR ─────────────────────────────────

@router.callback_query(OrderConfirmCD.filter())
async def cb_confirm_order(callback: CallbackQuery, callback_data: OrderConfirmCD, state: FSMContext, bot: Bot):
    plan_id = callback_data.plan_id
    user_id = callback.from_user.id

    try:
        pending = await count_pending_orders(user_id)
        if pending >= settings.MAX_PENDING_ORDERS:
            await callback.answer(
                f"⚠️ You already have {pending} pending orders.\n"
                "Please complete or wait for them to expire.",
                show_alert=True,
            )
            return

        bot_settings = await get_settings()
        upi_id = bot_settings.upi_id

        order = await create_order(user_id=user_id, plan_id=plan_id, upi_id=upi_id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    # Generate QR code
    qr_bytes = generate_upi_qr(
        upi_id=upi_id,
        amount=order.amount,
        order_id=order.order_id,
        name=bot_settings.upi_name,
    )

    timeout = bot_settings.payment_timeout_minutes
    text = (
        f"💳 <b>Payment Instructions</b>\n\n"
        f"📦 Product:  <b>{order.product_name}</b>\n"
        f"📋 Plan:     <b>{order.plan_name}</b>\n"
        f"💰 Amount:   <b>₹{order.amount:.0f}</b>\n"
        f"🆔 Order ID: <b>#{order.order_id}</b>\n\n"
        f"<b>UPI ID:</b> <code>{upi_id}</code>\n\n"
        f"Scan the QR code or copy the UPI ID to pay.\n"
        f"After payment, click <b>I've sent payment</b>.\n\n"
        f"⏳ This order expires in <b>{timeout} minutes</b>."
    )
    kb = payment_sent_kb(order.order_id)

    # Delete summary message, send photo with QR
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(qr_bytes.read(), filename="payment_qr.png"),
        caption=text,
        reply_markup=kb,
    )
    await callback.answer()


# ── "I've sent payment" → Ask for screenshot ─────────────────────────────────

@router.callback_query(UploadScreenshotCD.filter())
async def cb_upload_screenshot(callback: CallbackQuery, callback_data: UploadScreenshotCD, state: FSMContext):
    try:
        order_id = callback_data.order_id
        order = await get_order(order_id)
    except Exception as e:
        logger.error(f"Error getting order for screenshot upload: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not order or order.status != OrderStatus.pending:
        await callback.answer("Order not found or already processed.", show_alert=True)
        return

    await state.set_state(PaymentStates.waiting_screenshot)
    await state.update_data(order_id=order_id)

    await callback.message.answer(
        f"📸 <b>Send Payment Screenshot</b>\n\n"
        f"Please send a screenshot of your payment for order <b>#{order_id}</b>.\n\n"
        f"Make sure the screenshot shows:\n"
        f"• Amount paid\n"
        f"• UPI transaction ID\n"
        f"• Date and time",
        reply_markup=cancel_screenshot_kb(order_id),
    )
    await callback.answer()


# ── Receive Screenshot ────────────────────────────────────────────────────────

@router.message(PaymentStates.waiting_screenshot, F.photo)
async def handle_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")

    if not order_id:
        await state.clear()
        return

    try:
        order = await get_order(order_id)
        if not order or order.status != OrderStatus.pending:
            await state.clear()
            await message.answer(
                "⚠️ This order is no longer valid.",
                reply_markup=main_menu_kb(),
            )
            return

        # Save screenshot file_id
        file_id = message.photo[-1].file_id
        await submit_screenshot(order_id, file_id)
    except Exception as e:
        logger.error(f"Error submitting screenshot: {e}")
        await message.answer("⚠️ Something went wrong. Please try again or contact support.")
        return
    await state.clear()

    await message.answer(
        f"✅ <b>Screenshot received!</b>\n\n"
        f"Order: <b>#{order_id}</b>\n"
        f"Our team will verify your payment shortly.\n\n"
        f"You'll be notified once verified. Thank you! 🙏",
        reply_markup=main_menu_kb(),
    )

    # Notify payment admins
    await _notify_payment_admins(bot, order, file_id)


async def _notify_payment_admins(bot: Bot, order, file_id: str):
    """Forward screenshot + approve/reject buttons to all payment admins."""
    from keyboards.keyboards import payment_verify_kb

    try:
        admins = await get_admins_by_role(AdminRole.payment_admin, AdminRole.super_admin, AdminRole.owner)
    except Exception as e:
        logger.error(f"Error getting admins for notification: {e}")
        return

    username = order.user.username or order.user.full_name
    text = (
        f"💳 <b>Payment Verification</b>\n\n"
        f"👤 User:     @{username} (<code>{order.user_id}</code>)\n"
        f"🆔 Order:    <b>#{order.order_id}</b>\n"
        f"📦 Product:  {order.product_name}\n"
        f"📋 Plan:     {order.plan_name}\n"
        f"💰 Amount:   <b>₹{order.amount:.0f}</b>"
    )
    kb = payment_verify_kb(order.order_id)

    for admin in admins:
        try:
            await bot.send_photo(
                chat_id=admin.id,
                photo=file_id,
                caption=text,
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin.id}: {e}")


# ── Cancel Order ──────────────────────────────────────────────────────────────

@router.callback_query(CancelOrderCD.filter())
async def cb_cancel_order(callback: CallbackQuery, callback_data: CancelOrderCD, state: FSMContext):
    try:
        order_id = callback_data.order_id
        order = await get_order(order_id)

        if order and order.status in (OrderStatus.pending, OrderStatus.submitted):
            await update_order_status(order_id, OrderStatus.cancelled)
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Order cancelled.\n\nYou can create a new order anytime.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ── Non-photo in screenshot state ────────────────────────────────────────────

@router.message(PaymentStates.waiting_screenshot)
async def handle_non_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id", "")
    await message.answer(
        "⚠️ Please send a <b>photo/screenshot</b> of your payment.",
        reply_markup=cancel_screenshot_kb(order_id),
    )
