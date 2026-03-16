"""
handlers/admin/products.py
Product admin: add, edit, delete products and plans via FSM.
"""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.keyboards import (
    admin_product_actions_kb, admin_products_kb, back_to_admin_kb,
    AdminProductCD, AdminAddPlanCD, AdminDeleteProductCD, ConfirmDeleteProductCD,
    AdminEditProductCD,
)
from middlewares.role_filter import ProductAdminFilter
from services.db_service import (
    add_plan, create_product, delete_product, get_all_products,
    get_product, log_action, update_product,
)
from states.states import AddPlanStates, AddProductStates, EditProductStates

logger = logging.getLogger(__name__)
router = Router()


def _edit_fields_kb(product_id: int):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="Edit Emoji", callback_data="admin_edit_field:emoji")
    builder.button(text="Edit Name", callback_data="admin_edit_field:name")
    builder.button(text="Edit Tagline", callback_data="admin_edit_field:tagline")
    builder.button(text="Edit Description", callback_data="admin_edit_field:description")
    builder.button(text="Edit Requirements", callback_data="admin_edit_field:requirements_text")
    builder.button(text="Edit Category", callback_data="admin_edit_field:category")
    builder.button(text="Toggle Active", callback_data="admin_edit_field:is_active")
    builder.button(text="Back", callback_data=AdminProductCD(id=product_id).pack())
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


# ── Product List ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:products", ProductAdminFilter())
async def cb_products_list(callback: CallbackQuery):
    products = await get_all_products()
    kb = admin_products_kb(products)
    await callback.message.edit_text(
        f"📦 <b>Product Management</b>\n\n{len(products)} products total:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(AdminProductCD.filter(), ProductAdminFilter())
async def cb_product_actions(callback: CallbackQuery, callback_data: AdminProductCD):
    product_id = callback_data.id
    product = await get_product(product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    plans_text = "\n".join(
        f"  • {p.name} — ₹{p.price:.0f}" for p in product.plans if p.is_active
    ) or "  No plans yet"

    text = (
        f"{product.emoji or '🛍'} <b>{product.name}</b>\n"
        f"Category: {product.category}\n"
        f"Status: {'✅ Active' if product.is_active else '❌ Inactive'}\n\n"
        f"<b>Requirements:</b>\n{product.requirements_text or 'No extra requirements'}\n\n"
        f"<b>Plans:</b>\n{plans_text}"
    )
    await callback.message.edit_text(text, reply_markup=admin_product_actions_kb(product_id))
    await callback.answer()


@router.callback_query(AdminEditProductCD.filter(), ProductAdminFilter())
async def cb_edit_product_start(callback: CallbackQuery, callback_data: AdminEditProductCD, state: FSMContext):
    product_id = callback_data.id
    product = await get_product(product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    await state.set_state(EditProductStates.choosing_field)
    await state.update_data(edit_product_id=product_id)
    await callback.message.edit_text(
        f"<b>Edit Product</b>\n\n"
        f"Product: <b>{product.name}</b>\n\n"
        f"Choose what to update:",
        reply_markup=_edit_fields_kb(product_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_field:"), EditProductStates.choosing_field, ProductAdminFilter())
async def cb_choose_edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    product = await get_product(product_id) if product_id else None
    if not product_id or not product:
        await state.clear()
        await callback.answer("Edit session expired.", show_alert=True)
        return

    if field == "is_active":
        await update_product(product_id, is_active=not product.is_active)
        await log_action(callback.from_user.id, "edit_product", str(product_id), "toggle_active")
        updated = await get_product(product_id)
        status = "active" if updated and updated.is_active else "inactive"
        await state.clear()
        await callback.message.edit_text(
            f"Product <b>{product.name}</b> is now <b>{status}</b>.",
            reply_markup=admin_product_actions_kb(product_id),
        )
        await callback.answer("Product status updated.")
        return

    labels = {
        "emoji": "new product emoji",
        "name": "new product name",
        "tagline": "new tagline",
        "description": "new description",
        "requirements_text": "new requirements text (/skip to clear)",
        "category": "new category",
    }
    if field not in labels:
        await callback.answer("Invalid edit field.", show_alert=True)
        return

    await state.set_state(EditProductStates.new_value)
    await state.update_data(edit_field=field)
    await callback.message.answer(f"Send the {labels[field]} for <b>{product.name}</b>:")
    await callback.answer()


@router.message(EditProductStates.new_value, ProductAdminFilter())
async def step_edit_product_value(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    field = data.get("edit_field")
    if not product_id or not field:
        await state.clear()
        await message.answer("Edit session expired.", reply_markup=back_to_admin_kb())
        return

    value = message.text.strip()
    if field == "requirements_text" and message.text == "/skip":
        value = ""
    if not value and field != "requirements_text":
        await message.answer("Value cannot be empty. Please send a valid value.")
        return

    await update_product(product_id, **{field: value})
    await log_action(message.from_user.id, "edit_product", str(product_id), field)
    await state.clear()
    await message.answer(
        f"Product updated successfully.\n\nField: <b>{field}</b>\nValue: <b>{value}</b>",
        reply_markup=admin_product_actions_kb(product_id),
    )


# ── Add Product FSM ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_product", ProductAdminFilter())
async def cb_add_product_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProductStates.name)
    await callback.message.answer("📦 <b>Add New Product</b>\n\nStep 1/7: Send the <b>product name</b>:")
    await callback.answer()


@router.message(AddProductStates.name, ProductAdminFilter())
async def step_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 128:
        await message.answer("Product name must be between 1 and 128 characters. Please try again:")
        return
    await state.update_data(name=name)
    await state.set_state(AddProductStates.emoji)
    try:
        await message.answer(
            "Step 2/7: Send a <b>custom emoji</b> for this product button.\n"
            "Examples: 🎬 🎮 💻 📺 🔐\n"
            "Or send /skip to use 🛍."
        )
    except Exception as e:
        logger.exception("Error sending message")


@router.message(AddProductStates.emoji, ProductAdminFilter())
async def step_emoji(message: Message, state: FSMContext):
    emoji = "🛍" if message.text == "/skip" else message.text.strip()
    if not emoji:
        await message.answer("Please send one emoji or /skip.")
        return

    await state.update_data(emoji=emoji[:8])
    await state.set_state(AddProductStates.image)
    try:
        await message.answer(
            "Step 3/7: Send a <b>preview image</b> for this product.\n"
            "Or send /skip to skip."
        )
    except Exception as e:
        logger.exception("Error sending message")


@router.message(AddProductStates.image, ProductAdminFilter())
async def step_image(message: Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        await state.update_data(image_file_id=file_id)
    else:
        await state.update_data(image_file_id=None)

    await state.set_state(AddProductStates.tagline)
    await message.answer("Step 4/7: Send a <b>tagline</b> (short description, e.g. 'Pre Order Available'):")


@router.message(AddProductStates.tagline, ProductAdminFilter())
async def step_tagline(message: Message, state: FSMContext):
    text = message.text.strip() if message.text != "/skip" else ""
    await state.update_data(tagline=text)
    await state.set_state(AddProductStates.description)
    await message.answer("Step 5/7: Send the <b>product description</b> (details, validity, warranty, etc.):")


@router.message(AddProductStates.description, ProductAdminFilter())
async def step_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProductStates.requirements)
    await message.answer(
        "Step 6/7: Send <b>requirements text</b> that user must submit after payment.\n"
        "Example: account email, profile name, login ID, screenshot details.\n"
        "Or send /skip if no extra info is needed."
    )


@router.message(AddProductStates.requirements, ProductAdminFilter())
async def step_requirements(message: Message, state: FSMContext):
    requirements_text = "" if message.text == "/skip" else message.text.strip()
    await state.update_data(requirements_text=requirements_text)
    await state.set_state(AddProductStates.category)
    await message.answer(
        "Step 7/7: Send the <b>category</b> (e.g. OTT, Software, Gaming).\n"
        "Or send /skip for 'General':"
    )


@router.message(AddProductStates.category, ProductAdminFilter())
async def step_category(message: Message, state: FSMContext):
    category = "General" if message.text == "/skip" else message.text.strip()
    await state.update_data(category=category)
    await state.set_state(AddProductStates.plan_count)
    await message.answer("How many <b>plans</b> do you want to add? (Enter a number, e.g. 2):")


@router.message(AddProductStates.plan_count, ProductAdminFilter())
async def step_plan_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        assert 1 <= count <= 10
    except (ValueError, AssertionError):
        await message.answer("Please enter a valid number between 1 and 10.")
        return

    await state.update_data(plan_count=count, plans_added=0, plans=[])
    await state.set_state(AddProductStates.plan_name)
    await message.answer("Plan 1 — Send the <b>plan name</b> (e.g. '1 Month Without Pin'):")


@router.message(AddProductStates.plan_name, ProductAdminFilter())
async def step_plan_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 128:
        await message.answer("Plan name must be between 1 and 128 characters. Please try again:")
        return
    await state.update_data(current_plan_name=name)
    await state.set_state(AddProductStates.plan_price)
    await message.answer("Send the <b>price</b> for this plan (e.g. 109):")


@router.message(AddProductStates.plan_price, ProductAdminFilter())
async def step_plan_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
        if not (0 < price <= 99999):
            raise ValueError
    except ValueError:
        await message.answer("Please enter a valid positive price up to ₹99999.")
        return

    data = await state.get_data()
    plans = data.get("plans", [])
    plans.append({"name": data["current_plan_name"], "price": price})
    plans_added = data["plans_added"] + 1

    await state.update_data(plans=plans, plans_added=plans_added)

    if plans_added < data["plan_count"]:
        await state.set_state(AddProductStates.plan_name)
        await message.answer(f"Plan {plans_added + 1} — Send the <b>plan name</b>:")
    else:
        # Save everything
        await _save_product(message, state)


async def _save_product(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    product = await create_product(
        name=data["name"],
        emoji=data.get("emoji", "🛍"),
        tagline=data.get("tagline", ""),
        description=data.get("description", ""),
        requirements_text=data.get("requirements_text") or None,
        image_file_id=data.get("image_file_id"),
        category=data.get("category", "General"),
        created_by=message.from_user.id,
    )

    for plan_data in data.get("plans", []):
        await add_plan(product.id, plan_data["name"], plan_data["price"])

    await log_action(message.from_user.id, "add_product", str(product.id), product.name)
    await message.answer(
        f"✅ <b>Product Added!</b>\n\n"
        f"{product.emoji} <b>{product.name}</b> with {len(data['plans'])} plans created successfully.",
        reply_markup=back_to_admin_kb(),
    )


# ── Add Plan to Existing Product ──────────────────────────────────────────────

@router.callback_query(AdminAddPlanCD.filter(), ProductAdminFilter())
async def cb_add_plan_start(callback: CallbackQuery, callback_data: AdminAddPlanCD, state: FSMContext):
    product_id = callback_data.product_id
    await state.set_state(AddPlanStates.plan_name)
    await state.update_data(product_id=product_id)
    await callback.message.answer("Send the new <b>plan name</b>:")
    await callback.answer()


@router.message(AddPlanStates.plan_name, ProductAdminFilter())
async def add_plan_name(message: Message, state: FSMContext):
    await state.update_data(plan_name=message.text.strip())
    await state.set_state(AddPlanStates.plan_price)
    await message.answer("Send the <b>plan price</b> (e.g. 109):")


@router.message(AddPlanStates.plan_price, ProductAdminFilter())
async def add_plan_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("Invalid price. Please enter a number.")
        return

    data = await state.get_data()
    await add_plan(data["product_id"], data["plan_name"], price)
    await log_action(message.from_user.id, "add_plan", str(data["product_id"]))
    await state.clear()

    await message.answer(
        f"✅ Plan <b>{data['plan_name']}</b> (₹{price:.0f}) added!",
        reply_markup=back_to_admin_kb(),
    )


# ── Delete Product ────────────────────────────────────────────────────────────

@router.callback_query(AdminDeleteProductCD.filter(), ProductAdminFilter())
async def cb_delete_product(callback: CallbackQuery, callback_data: AdminDeleteProductCD):
    product_id = callback_data.id
    product = await get_product(product_id)

    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Yes, Delete", callback_data=ConfirmDeleteProductCD(id=product_id).pack())
    builder.button(text="◀️ Cancel",     callback_data=AdminProductCD(id=product_id).pack())
    builder.adjust(2)

    await callback.message.edit_text(
        f"⚠️ Delete <b>{product.name}</b>?\n\nThis action cannot be undone.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(ConfirmDeleteProductCD.filter(), ProductAdminFilter())
async def cb_confirm_delete(callback: CallbackQuery, callback_data: ConfirmDeleteProductCD):
    product_id = callback_data.id
    await delete_product(product_id)
    await log_action(callback.from_user.id, "delete_product", str(product_id))

    await callback.message.edit_text(
        "🗑 Product deleted successfully.",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()
