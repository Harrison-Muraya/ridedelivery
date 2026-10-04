"""Coordinate sanity checks for Kenya-focused rides."""

# Rough Kenya bounding box (includes border slack).
KENYA_LAT_MIN, KENYA_LAT_MAX = -5.0, 5.5
KENYA_LON_MIN, KENYA_LON_MAX = 33.5, 42.5


def _in_kenya(lat: float, lon: float) -> bool:
    return (
        KENYA_LAT_MIN <= lat <= KENYA_LAT_MAX
        and KENYA_LON_MIN <= lon <= KENYA_LON_MAX
    )


def _looks_swapped(lat: float, lon: float) -> bool:
    """True when values look like lon,lat (e.g. 36.82, -1.29) instead of lat,lon."""
    return (
        KENYA_LON_MIN <= lat <= KENYA_LON_MAX
        and KENYA_LAT_MIN <= lon <= KENYA_LAT_MAX
    )


def validate_kenya_coordinates(
    lat: float,
    lon: float,
    *,
    label: str = "coordinate",
) -> None:
    if _looks_swapped(lat, lon):
        raise ValueError(
            f"Invalid {label}: latitude/longitude appear swapped "
            f"(got lat={lat}, lon={lon}). "
            "Kenya latitudes are about -5..5 and longitudes about 34..42."
        )
    if not _in_kenya(lat, lon):
        raise ValueError(
            f"Invalid {label}: ({lat}, {lon}) is outside the supported Kenya area."
        )


def validate_trip_coordinates(
    pickup_lat: float,
    pickup_lon: float,
    dropoff_lat: float,
    dropoff_lon: float,
) -> None:
    validate_kenya_coordinates(pickup_lat, pickup_lon, label="pickup")
    validate_kenya_coordinates(dropoff_lat, dropoff_lon, label="dropoff")
    if pickup_lat == dropoff_lat and pickup_lon == dropoff_lon:
        raise ValueError("Pickup and dropoff coordinates must be different.")
