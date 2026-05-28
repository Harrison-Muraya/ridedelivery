from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.models.enums import BillingStatus, PaymentMethod


class BillingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    base_fare: Decimal
    distance_charge: Decimal
    time_charge: Decimal
    surge_charge: Decimal
    discount: Decimal
    total_amount: Decimal
    billing_status: BillingStatus
    payment_method: Optional[PaymentMethod]
    paid_at: Optional[datetime]
    rider_earnings: Optional[Decimal]
