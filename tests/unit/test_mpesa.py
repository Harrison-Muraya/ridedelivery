import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services import mpesa


def test_generate_password_is_base64_of_shortcode_passkey_timestamp(monkeypatch):
    monkeypatch.setattr(mpesa.settings, "MPESA_SHORTCODE", "174379")
    monkeypatch.setattr(mpesa.settings, "MPESA_PASSKEY", "secretpass")
    timestamp = "20260101120000"
    password = mpesa._generate_password(timestamp)
    expected = base64.b64encode(b"174379secretpass20260101120000").decode()
    assert password == expected


def test_base_url_sandbox_vs_prod(monkeypatch):
    monkeypatch.setattr(mpesa.settings, "MPESA_ENV", "sandbox")
    assert mpesa._base_url() == mpesa.SANDBOX_BASE
    monkeypatch.setattr(mpesa.settings, "MPESA_ENV", "production")
    assert mpesa._base_url() == mpesa.PROD_BASE


@pytest.mark.asyncio
async def test_stk_push_returns_mock_when_keys_missing(monkeypatch):
    monkeypatch.setattr(mpesa.settings, "MPESA_CONSUMER_KEY", "")
    response = await mpesa.stk_push(
        phone="+254712345678",
        amount=250.0,
        account_reference="REQ-1",
        description="Ride payment",
    )
    assert response["ResponseCode"] == "0"
    assert response["CheckoutRequestID"] == "mock-checkout-req"


@pytest.mark.asyncio
async def test_stk_push_calls_safaricom_when_configured(monkeypatch):
    monkeypatch.setattr(mpesa.settings, "MPESA_CONSUMER_KEY", "key")
    monkeypatch.setattr(mpesa.settings, "MPESA_CONSUMER_SECRET", "secret")
    monkeypatch.setattr(mpesa.settings, "MPESA_PASSKEY", "passkey")
    monkeypatch.setattr(mpesa.settings, "MPESA_SHORTCODE", "174379")
    monkeypatch.setattr(
        mpesa.settings,
        "MPESA_CALLBACK_URL",
        "https://example.com/callback",
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    token_resp = MagicMock()
    token_resp.raise_for_status = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}

    stk_resp = MagicMock()
    stk_resp.raise_for_status = MagicMock()
    stk_resp.json.return_value = {
        "MerchantRequestID": "m1",
        "CheckoutRequestID": "c1",
        "ResponseCode": "0",
    }

    mock_client.get.return_value = token_resp
    mock_client.post.return_value = stk_resp

    with patch("src.services.mpesa.httpx.AsyncClient", return_value=mock_client):
        result = await mpesa.stk_push(
            phone="+254712345678",
            amount=100,
            account_reference="ACC",
            description="Pay",
        )

    assert result["CheckoutRequestID"] == "c1"
    mock_client.post.assert_awaited()
