"""
services/xwallet_service.py
Async wrapper around the XWallet payment gateway APIs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

_CREATE_PAYMENT_URL = "https://xwalletbot.shop/pay.php"
_GET_QR_URL = "https://xwalletbot.shop/api_qr.php"
_CHECK_PAYMENT_URL = "https://xwalletbot.shop/check.php"


async def create_payment(amount: float, order_id: str) -> dict[str, Any]:
    """Create a pending XWallet payment for the given order amount."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _CREATE_PAYMENT_URL,
                params={"key": settings.XWALLET_API_KEY, "amount": amount},
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except Exception as e:
        logger.warning(f"XWallet create_payment failed for order {order_id}: {e}")
        raise

    if payload.get("status") != "pending":
        raise ValueError(f"Unexpected XWallet payment status: {payload.get('status')}")

    return payload


async def get_qr_image_url(qr_code_id: str) -> dict[str, Any]:
    """Fetch the QR image payload for an existing XWallet code."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _GET_QR_URL,
                params={"code": qr_code_id},
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
    except Exception as e:
        logger.warning(f"XWallet get_qr_image_url failed for code {qr_code_id}: {e}")
        raise


async def check_payment_status(qr_code_id: str) -> str:
    """Check the latest XWallet payment status for a QR code."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _CHECK_PAYMENT_URL,
                params={"code": qr_code_id},
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except Exception as e:
        logger.warning(f"XWallet check_payment_status failed for code {qr_code_id}: {e}")
        raise

    return str(payload.get("status", "FAILED"))


async def wait_for_payment(
    qr_code_id: str,
    timeout_minutes: int = 10,
    poll_interval: int = 5,
) -> bool:
    """Poll XWallet until the payment succeeds, fails, or times out."""
    deadline = asyncio.get_running_loop().time() + (timeout_minutes * 60)

    while asyncio.get_running_loop().time() < deadline:
        try:
            status = await check_payment_status(qr_code_id)
        except Exception as e:
            logger.warning(f"XWallet wait_for_payment retry for code {qr_code_id}: {e}")
            await asyncio.sleep(poll_interval)
            continue

        if status == "TXN_SUCCESS":
            return True
        if status == "FAILED":
            return False

        await asyncio.sleep(poll_interval)

    return False
