from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.misc import PricingConfig
from src.models.enums import RequestType
from src.services.distance import estimate_minutes


async def get_active_pricing(
    db: AsyncSession,
    request_type: RequestType,
    vehicle_type: str = "motorbike",
) -> Optional[PricingConfig]:
    result = await db.execute(
        select(PricingConfig).where(
            and_(
                PricingConfig.request_type == request_type,
                PricingConfig.vehicle_type == vehicle_type,
                PricingConfig.is_active == True,
            )
        )
    )
    return result.scalar_one_or_none()


async def calculate_fare(
    db: AsyncSession,
    request_type: RequestType,
    distance_km: float,
    vehicle_type: str = "motorbike",
) -> dict:
    """
    Returns a full fare breakdown dict.
    Falls back to hardcoded defaults if no pricing config exists.
    """
    config = await get_active_pricing(db, request_type, vehicle_type)

    if config:
        base_fare = Decimal(str(config.base_fare))
        per_km = Decimal(str(config.per_km_rate))
        per_min = Decimal(str(config.per_minute_rate))
        minimum = Decimal(str(config.minimum_fare))
        surge = Decimal(str(config.surge_multiplier))
    else:
        # Fallback defaults (KSH)
        base_fare = Decimal("50.00")
        per_km = Decimal("50.00")
        per_min = Decimal("2.00")
        minimum = Decimal("100.00")
        surge = Decimal("1.0")

    estimated_minutes = estimate_minutes(distance_km)
    dist = Decimal(str(round(distance_km, 2)))

    distance_charge = per_km * dist
    time_charge = per_min * Decimal(str(estimated_minutes))
    subtotal = (base_fare + distance_charge + time_charge) * surge
    total = max(subtotal, minimum)

    return {
        "base_fare": float(base_fare),
        "distance_charge": float(distance_charge),
        "time_charge": float(time_charge),
        "surge_charge": float((surge - 1) * (base_fare + distance_charge + time_charge)),
        "surge_multiplier": float(surge),
        "discount": 0.0,
        "total_amount": float(total),
        "estimated_minutes": estimated_minutes,
        "distance_km": float(dist),
    }
