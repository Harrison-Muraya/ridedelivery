import pytest

from src.services.distance import estimate_minutes, haversine_km
from src.services.geo import validate_kenya_coordinates, validate_trip_coordinates


def test_haversine_same_point_is_zero():
    assert haversine_km(-1.2921, 36.8219, -1.2921, 36.8219) == 0.0


def test_haversine_nairobi_to_westlands_roughly_5km():
    # CBD ≈ (-1.2864, 36.8172), Westlands ≈ (-1.2670, 36.8110)
    distance = haversine_km(-1.2864, 36.8172, -1.2670, 36.8110)
    assert 2.0 < distance < 4.0


def test_haversine_nairobi_to_kitengela_about_26km():
    # Address text alone is unused — only lat/lon matter.
    nairobi_cbd = (-1.286389, 36.817223)
    kitengela = (-1.473056, 36.956944)
    distance = haversine_km(*nairobi_cbd, *kitengela)
    assert 24.0 < distance < 30.0


def test_nearby_nairobi_pins_look_like_08km_bug():
    # Reproduces the reported ~0.8km when both pins are still in Nairobi.
    nairobi_a = (-1.286389, 36.817223)
    nairobi_b = (-1.2921, 36.8219)
    distance = haversine_km(*nairobi_a, *nairobi_b)
    assert 0.5 < distance < 1.2


def test_haversine_is_symmetric():
    a = haversine_km(-1.29, 36.82, -1.30, 36.90)
    b = haversine_km(-1.30, 36.90, -1.29, 36.82)
    assert abs(a - b) < 1e-9


def test_estimate_minutes_minimum_one():
    assert estimate_minutes(0.01, avg_speed_kmh=30.0) == 1


def test_estimate_minutes_typical_trip():
    # 15 km at 30 km/h → 30 minutes
    assert estimate_minutes(15.0, avg_speed_kmh=30.0) == 30


def test_rejects_swapped_lat_lon():
    with pytest.raises(ValueError, match="swapped"):
        validate_kenya_coordinates(36.817223, -1.286389, label="pickup")


def test_rejects_identical_pickup_dropoff():
    with pytest.raises(ValueError, match="must be different"):
        validate_trip_coordinates(-1.2864, 36.8172, -1.2864, 36.8172)
