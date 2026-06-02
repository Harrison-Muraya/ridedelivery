from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, model_validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
from uuid import UUID 
from src.models.enums import UserRole



class UserCreate(BaseModel):
    email: EmailStr
    phone: str
    password: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.customer

    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        v = v.strip().replace(" ", "")
        if not v.startswith("+"):
            v = "+254" + v.lstrip("0")
        return v


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    is_available: bool
    rating_avg: float
    rating_count: int
    total_trips: int
    wallet_balance: Decimal


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str
    role: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    profile: Optional[ProfileOut] = None
    roles: List[str] = []

    @model_validator(mode="before")
    @classmethod
    def extract_roles_and_role(cls, obj):
        if hasattr(obj, "roles") and obj.roles:
            role_strings = [
                r.role.value if hasattr(r, "role") else str(r)
                for r in obj.roles
            ]
            # Don't mutate the ORM object — return a dict instead
            data = {
                "id": obj.id,
                "email": obj.email,
                "phone": obj.phone,
                "is_active": obj.is_active,
                "is_verified": obj.is_verified,
                "created_at": obj.created_at,
                "profile": obj.profile,
                "roles": role_strings,
                "role": role_strings[0] if role_strings else None,
            }
            return data
        return obj

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, "_role_str"):
            instance.role = obj._role_str
        elif instance.roles:
            instance.role = instance.roles[0]
        return instance

# class UserResponse(BaseModel):
#     model_config = ConfigDict(from_attributes=True)

#     id: UUID
#     email: str
#     phone: str
#     role: Optional[str] = None       # extracted via validator below
#     is_active: bool
#     is_verified: bool
#     created_at: datetime
#     profile: Optional[ProfileOut] = None
#     roles: List[str] = [] 
    

#     @model_validator(mode="before")
#     @classmethod
#     def extract_role(cls, obj):
#         # obj is the ORM User instance when from_attributes=True
#         if hasattr(obj, "roles") and obj.roles:
#             # roles is a list of UserRoleMap; take the first role's value
#             object.__setattr__(obj, "_role_str", obj.roles[0].role.value)
#         return obj


#     @classmethod
#     def model_validate(cls, obj, **kwargs):
#         instance = super().model_validate(obj, **kwargs)
#         # Inject the role we extracted above
#         if hasattr(obj, "_role_str"):
#             instance.role = obj._role_str
#         elif hasattr(obj, "roles") and obj.roles:
#             instance.role = obj.roles[0].role.value
#         return instance
    

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

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    email: Optional[EmailStr] = None
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str
