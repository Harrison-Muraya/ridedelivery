from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.enums import RequestType
from src.services.fare import calculate_fare


@pytest.mark.asyncio
async def test_calculate_fare_uses_fallback_defaults_when_no_config():
    db = AsyncMock()
    # get_active_pricing path: db.execute(...).scalar_one_or_none()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    breakdown = await calculate_fare(db, RequestType.ride, distance_km=2.0)

    assert breakdown["base_fare"] == 50.0
    assert breakdown["distance_charge"] == 100.0  # 50 * 2
    assert breakdown["surge_multiplier"] == 1.0
    assert breakdown["distance_km"] == 2.0
    assert breakdown["estimated_minutes"] >= 1
    # subtotal = (50 + 100) * 1 = 150 → above minimum 100
    assert breakdown["total_amount"] == 150.0


@pytest.mark.asyncio
async def test_calculate_fare_enforces_minimum():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    breakdown = await calculate_fare(db, RequestType.ride, distance_km=0.1)

    # base 50 + distance 5 = 55, below minimum 100
    assert breakdown["total_amount"] == 100.0


@pytest.mark.asyncio
async def test_calculate_fare_uses_pricing_config():
    db = AsyncMock()
    config = MagicMock()
    config.base_fare = Decimal("80.00")
    config.per_km_rate = Decimal("40.00")
    config.per_minute_rate = Decimal("3.00")
    config.minimum_fare = Decimal("120.00")
    config.surge_multiplier = Decimal("1.5")

    result = MagicMock()
    result.scalar_one_or_none.return_value = config
    db.execute.return_value = result

    breakdown = await calculate_fare(
        db, RequestType.delivery, distance_km=3.0, vehicle_type="motorbike"
    )

    assert breakdown["base_fare"] == 80.0
    assert breakdown["distance_charge"] == 120.0  # 40 * 3
    assert breakdown["surge_multiplier"] == 1.5
    # (80 + 120) * 1.5 = 300
    assert breakdown["total_amount"] == 300.0
