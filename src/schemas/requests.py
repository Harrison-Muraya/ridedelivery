from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.models.enums import RequestType, RequestStatus, AssignmentStatus


class CreateRideRequest(BaseModel):
    request_type: RequestType
    pickup_latitude: float
    pickup_longitude: float
    pickup_address: str
    dropoff_latitude: float
    dropoff_longitude: float
    dropoff_address: str
    preferred_rider_id: Optional[UUID] = None
    package_description: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    request_type: RequestType
    request_status: RequestStatus
    pickup_address: str
    dropoff_address: str
    distance_km: Optional[float]
    estimated_minutes: Optional[int]
    estimated_fare: Optional[Decimal]
    final_fare: Optional[Decimal]
    created_at: datetime
    accepted_at: Optional[datetime]
    completed_at: Optional[datetime]


class FareEstimateOut(BaseModel):
    distance_km: float
    estimated_minutes: int
    estimated_fare: Decimal
    breakdown: dict


class AssignmentResponseRequest(BaseModel):
    accept: bool
    rejection_reason: Optional[str] = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    rider_id: UUID
    assignment_status: AssignmentStatus
    attempt_number: int
    created_at: datetime
