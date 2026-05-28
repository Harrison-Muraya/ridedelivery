

"""
M-Pesa Daraja callback endpoint.
Safaricom POSTs here asynchronously after an STK push completes or fails.
"""

from fastapi import APIRouter, Request, HTTPException
from src.jobs.payment_tasks import process_mpesa_callback

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/mpesa/callback")
async def mpesa_callback(request: Request):
    """
    Receive M-Pesa STK push result from Safaricom.
    We hand off processing to a Celery task immediately so Safaricom
    gets a fast 200 response (they retry on timeout).
    """
    body = await request.json()

    try:
        stk_callback = body["Body"]["stkCallback"]
        checkout_request_id = stk_callback["CheckoutRequestID"]
        result_code = stk_callback["ResultCode"]

        receipt_number = None
        if result_code == 0:
            items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item.get("Name") == "MpesaReceiptNumber":
                    receipt_number = item.get("Value")
                    break

        process_mpesa_callback.delay(checkout_request_id, result_code, receipt_number)

    except (KeyError, TypeError) as e:
        # Log but always return 200 to Safaricom
        import logging
        logging.getLogger(__name__).error("Malformed M-Pesa callback: %s | body: %s", e, body)

    return {"ResultCode": 0, "ResultDesc": "Accepted"}
