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
_HTTP_TIMEOUT_SECONDS = 15
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_CREATE_PAYMENT_RETRIES = 3
_GET_QR_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 1.0


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, aiohttp.ClientResponseError):
        return error.status in _RETRYABLE_STATUS_CODES
    return isinstance(
        error,
        (
            aiohttp.ClientConnectionError,
            aiohttp.ClientPayloadError,
            aiohttp.ServerTimeoutError,
            asyncio.TimeoutError,
        ),
    )


async def _get_json_with_retries(
    url: str,
    params: dict[str, Any],
    *,
    retries: int,
    context: str,
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
                    if not isinstance(payload, dict):
                        raise ValueError(f"Unexpected XWallet payload type: {type(payload).__name__}")
                    return payload
        except Exception as error:
            last_error = error
            is_retryable = _is_retryable_error(error)
            if attempt >= retries or not is_retryable:
                raise

            delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "XWallet %s transient error on attempt %d/%d: %s. Retrying in %.1fs",
                context,
                attempt,
                retries,
                error,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError(f"XWallet {context} failed after retries: {last_error}")


async def create_payment(amount: float, order_id: str) -> dict[str, Any]:
    """Create a pending XWallet payment for the given order amount."""
    try:
        if not settings.XWALLET_API_KEY:
            raise ValueError("XWALLET_API_KEY is not configured")
        payload = await _get_json_with_retries(
            _CREATE_PAYMENT_URL,
            params={"key": settings.XWALLET_API_KEY, "amount": amount},
            retries=_CREATE_PAYMENT_RETRIES,
            context=f"create_payment for order {order_id}",
        )
    except Exception as e:
        logger.warning(f"XWallet create_payment failed for order {order_id}: {e}")
        raise

    if str(payload.get("status", "")).lower() != "pending":
        raise ValueError(f"Unexpected XWallet payment status: {payload.get('status')}")

    return payload


async def get_qr_image_url(qr_code_id: str) -> dict[str, Any]:
    """Fetch the QR image payload for an existing XWallet code."""
    try:
        return await _get_json_with_retries(
            _GET_QR_URL,
            params={"code": qr_code_id},
            retries=_GET_QR_RETRIES,
            context=f"get_qr_image_url for code {qr_code_id}",
        )
    except Exception as e:
        logger.warning(f"XWallet get_qr_image_url failed for code {qr_code_id}: {e}")
        raise


async def check_payment_status(qr_code_id: str) -> str:
    """Check the latest XWallet payment status for a QR code."""
    try:
        payload = await _get_json_with_retries(
            _CHECK_PAYMENT_URL,
            params={"code": qr_code_id},
            retries=1,
            context=f"check_payment_status for code {qr_code_id}",
        )
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
