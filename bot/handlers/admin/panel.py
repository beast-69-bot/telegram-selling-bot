"""
handlers/admin/panel.py
/admin command: show admin panel and stats.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database.models import AdminRole
from keyboards.keyboards import ToggleBanCD, admin_panel_kb, admin_recent_users_kb, back_to_admin_kb
from middlewares.role_filter import AnyAdminFilter, OwnerOrSuperFilter
from services.db_service import get_admin, get_recent_users, get_stats, toggle_user_ban

router = Router()


def _can_view_all_orders(role: AdminRole | None) -> bool:
    return role in (AdminRole.owner, AdminRole.super_admin)


@router.message(Command("admin"), AnyAdminFilter())
async def cmd_admin(message: Message):
    await _show_panel(message)


@router.callback_query(F.data == "admin:panel", AnyAdminFilter())
async def cb_admin_panel(callback: CallbackQuery):
    await _show_panel(callback)
    await callback.answer()


async def _show_panel(target: Message | CallbackQuery):
    admin = await get_admin(target.from_user.id)
    show_all_orders = _can_view_all_orders(admin.role if admin else None)

    text = "<b>Admin Panel</b>\n\nWhat would you like to manage?"
    kb = admin_panel_kb(show_all_orders=show_all_orders)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "admin:stats", AnyAdminFilter())
async def cb_stats(callback: CallbackQuery):
    stats = await get_stats()
    text = (
        "<b>Bot Statistics</b>\n\n"
        f"Total Users: <b>{stats['total_users']}</b>\n"
        f"Total Orders: <b>{stats['total_orders']}</b>\n"
        f"Paid Orders: <b>{stats['paid_orders']}</b>\n"
        f"Delivered: <b>{stats['delivered']}</b>\n"
        f"Total Revenue: <b>Rs {stats['total_revenue']:.0f}</b>\n"
        f"Pending Verify: <b>{stats['pending_verify']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:ban", OwnerOrSuperFilter())
async def cb_admin_ban(callback: CallbackQuery):
    users = await get_recent_users(20)
    kb = admin_recent_users_kb(users)
    await callback.message.edit_text(
        "<b>Ban/Unban Users</b>\n\nSelect a user to toggle status (recent 20):",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(ToggleBanCD.filter(), OwnerOrSuperFilter())
async def cb_toggle_ban(callback: CallbackQuery, callback_data: ToggleBanCD):
    user_id = callback_data.user_id
    is_banned = await toggle_user_ban(user_id)
    status = "Banned" if is_banned else "Unbanned"
    await callback.answer(f"User {user_id} {status}.", show_alert=True)
    await cb_admin_ban(callback)
