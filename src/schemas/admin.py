from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.models.enums import RequestType


class UpdatePricingRequest(BaseModel):
    request_type: RequestType
    vehicle_type: str = "motorbike"
    base_fare: Decimal
    per_km_rate: Decimal
    per_minute_rate: Decimal
    minimum_fare: Decimal
    surge_multiplier: float = 1.0


class AdminAssignRiderRequest(BaseModel):
    request_id: UUID
    rider_id: UUID


class PricingConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_type: RequestType
    vehicle_type: str
    base_fare: Decimal
    per_km_rate: Decimal
    per_minute_rate: Decimal
    minimum_fare: Decimal
    surge_multiplier: float
    is_active: bool
