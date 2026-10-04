from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_login_and_me(client):
    suffix = uuid4().hex[:8]
    email = f"customer_{suffix}@example.com"
    payload = {
        "email": email,
        "phone": f"07{suffix[:8]}",
        "password": "SecurePass123!",
        "first_name": "Ada",
        "last_name": "Mwangi",
        "role": "customer",
    }

    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, register.text
    user = register.json()
    assert user["email"] == email
    assert user["phone"].startswith("+254")
    assert "customer" in user["roles"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client, register_user):
    user = await register_user(email="dup@example.com")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user.email,
            "phone": "+254700000099",
            "password": "SecurePass123!",
            "first_name": "Other",
            "last_name": "User",
            "role": "customer",
        },
    )
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_invalid_credentials(client, register_user):
    user = await register_user()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_token(client, register_user):
    user = await register_user()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "SecurePass123!"},
    )
    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    assert refresh.json()["access_token"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_requires_auth(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)
