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
        v = v.strip().replace(" ", "")
        if not v.startswith("+"):
            v = "+254" + v.lstrip("0")
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
