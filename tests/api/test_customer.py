import pytest
from src.models.enums import UserRole


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fare_estimate_requires_customer_role(client, auth_headers):
    headers = await auth_headers(role=UserRole.customer)
    response = await client.get(
        "/api/v1/customer/fare-estimate",
        params={
            "pickup_lat": -1.2864,
            "pickup_lon": 36.8172,
            "dropoff_lat": -1.2670,
            "dropoff_lon": 36.8110,
            "request_type": "ride",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["distance_km"] > 0
    # Decimal fields are JSON-serialized as strings by Pydantic
    assert float(body["estimated_fare"]) >= 100
    assert "breakdown" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fare_estimate_forbidden_for_rider(client, auth_headers):
    headers = await auth_headers(role=UserRole.rider)
    response = await client.get(
        "/api/v1/customer/fare-estimate",
        params={
            "pickup_lat": -1.2864,
            "pickup_lon": 36.8172,
            "dropoff_lat": -1.2670,
            "dropoff_lon": 36.8110,
        },
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_customer_profile(client, auth_headers):
    headers = await auth_headers(role=UserRole.customer)
    response = await client.get("/api/v1/customer/profile", headers=headers)
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["first_name"] == "Test"
    assert profile["last_name"] == "User"
