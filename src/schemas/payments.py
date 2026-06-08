from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator, ConfigDict
from src.models.enums import PaymentMethod, TransactionStatus


class InitiatePaymentRequest(BaseModel):
    billing_id: UUID
    phone: str
    payment_method: PaymentMethod = PaymentMethod.mpesa

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v):
        v = v.strip().replace(" ", "").replace("-", "")

        # +254712345678 → 254712345678
        if v.startswith("+254"):
            v = v[1:]  # just strip the +

        # +07... or other malformed + numbers
        elif v.startswith("+"):
            raise ValueError("Invalid phone number format")

        # 0712345678 → 254712345678
        elif v.startswith("0") and len(v) == 10:
            v = "254" + v[1:]  # replace leading 0 with 254, not lstrip

        # 712345678 (9 digits, no prefix)
        elif len(v) == 9 and v.startswith("7") or v.startswith("1"):
            v = "254" + v

        # already 254712345678
        elif v.startswith("254") and len(v) == 12:
            pass

        else:
            raise ValueError(
                "Invalid phone number. Use format: 0712345678, +254712345678, or 254712345678"
            )

        # Final sanity check — must be 12 digits, all numeric
        if not v.isdigit() or len(v) != 12:
            raise ValueError("Phone number must be 12 digits after normalization")

        return v


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    billing_id: UUID
    amount: Decimal
    payment_method: PaymentMethod
    transaction_status: TransactionStatus
    mpesa_checkout_request_id: Optional[str]
    mpesa_receipt_number: Optional[str]
    created_at: datetime
