import base64
import logging
from datetime import datetime
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
PROD_BASE = "https://api.safaricom.co.ke"


def _base_url() -> str:
    return SANDBOX_BASE if settings.MPESA_ENV == "sandbox" else PROD_BASE


async def _get_access_token() -> str:
    url = f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def _generate_password(timestamp: str) -> str:
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


async def stk_push(
    phone: str,
    amount: float,
    account_reference: str,
    description: str,
) -> dict:
    """
    Initiate an STK Push (Lipa Na M-Pesa Online).
    Returns the full Safaricom API response.
    """
    if not settings.MPESA_CONSUMER_KEY:
        # Return mock response in dev/test when keys are not configured
        logger.warning("M-Pesa keys not configured — returning mock STK push response")
        return {
            "MerchantRequestID": "mock-merchant-req",
            "CheckoutRequestID": "mock-checkout-req",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        }

    token = await _get_access_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = _generate_password(timestamp)

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone.lstrip("+"),
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone.lstrip("+"),
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": description,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def query_stk_status(checkout_request_id: str) -> dict:
    """Query status of an STK push."""
    token = await _get_access_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = _generate_password(timestamp)

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
