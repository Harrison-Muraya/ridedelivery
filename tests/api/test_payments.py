from unittest.mock import MagicMock

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mpesa_callback_accepts_valid_payload(client, monkeypatch):
    delay = MagicMock()
    monkeypatch.setattr(
        "src.api.v1.payments.process_mpesa_callback.delay",
        delay,
    )

    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_CO_123",
                "ResultCode": 0,
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "MpesaReceiptNumber", "Value": "QK123ABC"},
                        {"Name": "Amount", "Value": 250},
                    ]
                },
            }
        }
    }

    response = await client.post("/api/v1/payments/mpesa/callback", json=payload)
    assert response.status_code == 200
    assert response.json()["ResultCode"] == 0
    delay.assert_called_once_with("ws_CO_123", 0, "QK123ABC")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mpesa_callback_malformed_still_returns_200(client, monkeypatch):
    delay = MagicMock()
    monkeypatch.setattr(
        "src.api.v1.payments.process_mpesa_callback.delay",
        delay,
    )

    response = await client.post(
        "/api/v1/payments/mpesa/callback",
        json={"unexpected": True},
    )
    assert response.status_code == 200
    assert response.json()["ResultCode"] == 0
    delay.assert_not_called()
