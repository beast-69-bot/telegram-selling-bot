"""
states/states.py
All FSM state groups for Aiogram.
"""

from aiogram.fsm.state import State, StatesGroup


# ── User States ───────────────────────────────────────────────────────────────

class PaymentStates(StatesGroup):
    waiting_screenshot = State()


class ProductSearchStates(StatesGroup):
    waiting_query = State()


# ── Admin: Product Management ─────────────────────────────────────────────────

class AddProductStates(StatesGroup):
    name        = State()
    emoji       = State()
    image       = State()
    tagline     = State()
    description = State()
    category    = State()
    plan_count  = State()
    plan_name   = State()
    plan_price  = State()


class EditProductStates(StatesGroup):
    choosing_field = State()
    new_value      = State()


class AddPlanStates(StatesGroup):
    plan_name  = State()
    plan_price = State()


# ── Admin: Settings ───────────────────────────────────────────────────────────

class SettingsStates(StatesGroup):
    setting_upi = State()


# ── Admin: Admins Management ──────────────────────────────────────────────────

class AdminManagementStates(StatesGroup):
    waiting_user_id = State()
    choosing_role   = State()


# ── Admin: Broadcast ──────────────────────────────────────────────────────────

class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirming      = State()


# ── Admin: Payment Rejection ──────────────────────────────────────────────────

class RejectPaymentStates(StatesGroup):
    waiting_reason = State()


# ── Admin: Order Delivery ─────────────────────────────────────────────────────

class DeliverOrderStates(StatesGroup):
    waiting_product = State()


class ContactUserStates(StatesGroup):
    waiting_message = State()
