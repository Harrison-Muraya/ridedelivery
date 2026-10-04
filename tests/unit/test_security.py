from datetime import timedelta

from jose import jwt
from src.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("MySecret123!")
    assert hashed != "MySecret123!"
    assert verify_password("MySecret123!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_access_token_contains_claims():
    token = create_access_token(
        data={"sub": "rider@example.com", "user_id": "abc-123"},
        expires_delta=timedelta(minutes=5),
    )
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "rider@example.com"
    assert payload["user_id"] == "abc-123"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_create_refresh_token_type():
    token = create_refresh_token(data={"sub": "a@b.com", "user_id": "u1"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["type"] == "refresh"
