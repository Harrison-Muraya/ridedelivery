from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    avatar_url: Optional[str]
    vehicle_type: Optional[str]
    vehicle_plate: Optional[str]
    is_available: bool
    rating_avg: float
    rating_count: int
    total_trips: int
    wallet_balance: Decimal


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    phone: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    profile: Optional[ProfileOut]


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    national_id: Optional[str] = None


class RiderAvailabilityRequest(BaseModel):
    is_available: bool
    latitude: float
    longitude: float


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    heading: Optional[float] = None
    accuracy: Optional[float] = None
