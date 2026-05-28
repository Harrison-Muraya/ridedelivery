import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.models.user import User, UserProfile, UserLocation, UserRoleMap
from src.models.requests import Request, RequestAssignment
from src.models.enums import UserRole, AssignmentStatus, RequestStatus
from src.services.distance import haversine_km
from src.config import settings

logger = logging.getLogger(__name__)


async def find_nearest_available_riders(
    db: AsyncSession,
    pickup_lat: float,
    pickup_lon: float,
    radius_km: float,
    exclude_rider_ids: Optional[List[UUID]] = None,
    preferred_rider_id: Optional[UUID] = None,
) -> List[tuple]:
    """
    Returns a list of (rider User, distance_km) sorted by distance ascending.
    Checks the user_locations table for proximity and user_profiles for availability.
    """
    exclude_ids = set(exclude_rider_ids or [])

    # Fetch all available riders with location loaded
    stmt = (
        select(User)
        .join(UserProfile, UserProfile.user_id == User.id)
        .join(UserLocation, UserLocation.user_id == User.id)
        .join(UserRoleMap, UserRoleMap.user_id == User.id)
        .where(
            and_(
                UserRoleMap.role == UserRole.rider,
                UserProfile.is_available == True,
                User.is_active == True,
            )
        )
        .options(
            selectinload(User.profile),
            selectinload(User.location),
        )
    )
    result = await db.execute(stmt)
    riders = result.scalars().unique().all()

    candidates = []
    for rider in riders:
        if rider.id in exclude_ids:
            continue
        if not rider.location:
            continue
        dist = haversine_km(
            pickup_lat, pickup_lon,
            rider.location.latitude, rider.location.longitude,
        )
        if dist <= radius_km:
            candidates.append((rider, dist))

    # Put preferred rider first if within radius
    if preferred_rider_id:
        candidates.sort(key=lambda x: (x[0].id != preferred_rider_id, x[1]))
    else:
        candidates.sort(key=lambda x: x[1])

    return candidates


async def get_next_rider_for_request(
    db: AsyncSession,
    request: Request,
) -> Optional[tuple]:
    """
    Determines the next rider to try, expanding search radius on each attempt.
    Returns (rider, distance_km) or None if no riders found.
    """
    # Collect already-tried rider IDs from previous assignments
    tried_ids = [a.rider_id for a in request.assignments]
    attempt_number = len(tried_ids) + 1

    # Expand search radius with each attempt
    radius_km = min(
        settings.INITIAL_SEARCH_RADIUS_KM * attempt_number,
        settings.MAX_SEARCH_RADIUS_KM,
    )

    candidates = await find_nearest_available_riders(
        db,
        pickup_lat=request.pickup_latitude,
        pickup_lon=request.pickup_longitude,
        radius_km=radius_km,
        exclude_rider_ids=tried_ids,
        preferred_rider_id=request.preferred_rider_id,
    )

    return candidates[0] if candidates else None
