"""
handlers/user/products.py
Product browsing with pagination, product detail, plan selection.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from keyboards.keyboards import (
    main_menu_kb, order_confirm_kb, plans_kb, product_detail_kb, products_page_kb,
    BrowseProductsCD, ProductCD, PlansCD, SelectPlanCD
)
from services.db_service import (
    get_plan, get_product, get_products_page, search_products,
)
from states.states import ProductSearchStates

router = Router()


# ── Product Listing (Paginated) ───────────────────────────────────────────────

@router.callback_query(BrowseProductsCD.filter())
async def cb_browse_products(callback: CallbackQuery, callback_data: BrowseProductsCD, state: FSMContext):
    try:
        page = callback_data.page
        products, total = await get_products_page(page)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB Error in products list: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not products:
        await callback.answer("No products available right now.", show_alert=True)
        return

    text = "🛍 <b>Our Products</b>\n\nSelect a product to view details:"
    kb = products_page_kb(products, page, total)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Product Detail ────────────────────────────────────────────────────────────

@router.callback_query(ProductCD.filter())
async def cb_product_detail(callback: CallbackQuery, callback_data: ProductCD, state: FSMContext):
    try:
        product_id = callback_data.id
        product = await get_product(product_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB Error in product detail: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    # Build product detail text
    plans_text = ""
    for plan in product.plans:
        if plan.is_active:
            plans_text += f"  • {plan.name} — <b>₹{plan.price:.0f}</b>\n"

    text = (
        f"<b>{product.name}</b>\n"
        f"<i>{product.tagline or ''}</i>\n\n"
        f"{product.description or ''}\n\n"
        f"<b>📋 Available Plans:</b>\n{plans_text}"
    )

    # Remember which page user came from (default 0)
    await state.update_data(product_page=0)
    kb = product_detail_kb(product_id, page=0)

    # If product has an image, send as photo; else edit text
    if product.image_file_id:
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=product.image_file_id,
                caption=text,
                reply_markup=kb,
            )
        except Exception:
            await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.edit_text(text, reply_markup=kb)

    await callback.answer()


# ── Plan Selection ────────────────────────────────────────────────────────────

@router.callback_query(PlansCD.filter())
async def cb_plans(callback: CallbackQuery, callback_data: PlansCD):
    try:
        product_id = callback_data.product_id
        product = await get_product(product_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB Error in plans: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not product or not product.plans:
        await callback.answer("No plans available.", show_alert=True)
        return

    active_plans = [p for p in product.plans if p.is_active]
    if not active_plans:
        await callback.answer("No active plans.", show_alert=True)
        return

    text = f"<b>{product.name}</b>\n\n💳 <b>Select a Plan:</b>"
    kb = plans_kb(active_plans, product_id)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        # If message has a photo, need to send new message
        await callback.message.answer(text, reply_markup=kb)

    await callback.answer()


# ── Order Summary (Before Confirming) ────────────────────────────────────────

@router.callback_query(SelectPlanCD.filter())
async def cb_select_plan(callback: CallbackQuery, callback_data: SelectPlanCD, state: FSMContext):
    try:
        plan_id = callback_data.plan_id
        plan = await get_plan(plan_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB Error in select_plan: {e}")
        await callback.answer("⚠️ Something went wrong. Please try again or contact support.", show_alert=True)
        return

    if not plan:
        await callback.answer("Plan not found.", show_alert=True)
        return

    text = (
        f"🛒 <b>Order Summary</b>\n\n"
        f"Product: <b>{plan.product.name}</b>\n"
        f"Plan:    <b>{plan.name}</b>\n"
        f"Amount:  <b>₹{plan.price:.0f}</b>\n\n"
        f"Confirm your order?"
    )
    kb = order_confirm_kb(plan_id)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)

    await callback.answer()


# ── Product Search ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "search_products")
async def cb_search_products(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductSearchStates.waiting_query)
    await callback.message.edit_text(
        "🔍 <b>Search Products</b>\n\n"
        "Enter the name or keywords of the product you're looking for:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.message(ProductSearchStates.waiting_query, F.text)
async def handle_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("⚠️ Please enter at least 2 characters to search.")
        return

    try:
        products = await search_products(query)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB Error in search: {e}")
        await message.answer("⚠️ Something went wrong. Please try again or contact support.")
        return
    await state.clear()

    if not products:
        await message.answer(
            f"❌ No products found for '<b>{query}</b>'.\n\n"
            "Try again or browse all products.",
            reply_markup=main_menu_kb()
        )
        return

    text = f"🔍 <b>Search results for '{query}':</b>"
    
    # Simple list for search results (reusing products_page_kb logic but for search)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for p in products[:10]: # Limit to 10 results
        kb.button(text=f"🟢 {p.name}", callback_data=f"product:{p.id}")
    
    kb.button(text="🏠 Main Menu", callback_data="main_menu")
    kb.adjust(1)
    
    from aiogram.enums import ParseMode
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
