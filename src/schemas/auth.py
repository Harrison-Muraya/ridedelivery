from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from src.models.enums import UserRole


class RegisterRequest(BaseModel):
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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
