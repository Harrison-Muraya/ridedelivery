from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
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


class UpdateAssignmentConfigRequest(BaseModel):
    rider_response_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    max_search_radius_km: float = Field(default=10.0, gt=0, le=100)
    initial_search_radius_km: float = Field(default=3.0, gt=0, le=100)
    max_assignment_attempts: int = Field(default=5, ge=1, le=50)


class AssignmentConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    rider_response_timeout_seconds: int
    max_search_radius_km: float
    initial_search_radius_km: float
    max_assignment_attempts: int
    source: str = "defaults"
