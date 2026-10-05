"""Road-distance routing via OSRM, with haversine fallback."""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

import httpx

from src.config import settings
from src.services.distance import estimate_minutes, haversine_km

logger = logging.getLogger(__name__)


class RouteResult(TypedDict):
    distance_km: float
    duration_minutes: int
    source: str  # "osrm" | "haversine"


async def road_route(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> RouteResult:
    """
    Return driving distance/duration between two points.

    Uses OSRM when ROUTING_ENABLED is true; falls back to straight-line
    haversine if routing is disabled or the request fails.
    """
    if settings.ROUTING_ENABLED:
        routed = await _osrm_route(lat1, lon1, lat2, lon2)
        if routed is not None:
            return routed
        logger.warning(
            "OSRM routing failed; falling back to haversine (%.5f,%.5f -> %.5f,%.5f)",
            lat1, lon1, lat2, lon2,
        )

    straight = haversine_km(lat1, lon1, lat2, lon2)
    return {
        "distance_km": round(straight, 2),
        "duration_minutes": estimate_minutes(straight),
        "source": "haversine",
    }


async def _osrm_route(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[RouteResult]:
    # OSRM expects lon,lat (not lat,lon)
    base = settings.OSRM_BASE_URL.rstrip("/")
    url = (
        f"{base}/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
        f"?overview=false&alternatives=false&steps=false"
    )
    try:
        async with httpx.AsyncClient(timeout=settings.OSRM_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # network / parse / unexpected client errors
        logger.warning("OSRM request error: %s", exc)
        return None

    if payload.get("code") != "Ok":
        logger.warning("OSRM non-Ok response: %s", payload.get("code"))
        return None

    routes = payload.get("routes") or []
    if not routes:
        return None

    route = routes[0]
    distance_m = float(route.get("distance") or 0.0)
    duration_s = float(route.get("duration") or 0.0)
    if distance_m <= 0:
        return None

    return {
        "distance_km": round(distance_m / 1000.0, 2),
        "duration_minutes": max(1, round(duration_s / 60.0)),
        "source": "osrm",
    }
