from src.services.distance import estimate_minutes, haversine_km


def test_haversine_same_point_is_zero():
    assert haversine_km(-1.2921, 36.8219, -1.2921, 36.8219) == 0.0


def test_haversine_nairobi_to_westlands_roughly_5km():
    # CBD ≈ (-1.2864, 36.8172), Westlands ≈ (-1.2670, 36.8110)
    distance = haversine_km(-1.2864, 36.8172, -1.2670, 36.8110)
    assert 2.0 < distance < 4.0


def test_haversine_is_symmetric():
    a = haversine_km(-1.29, 36.82, -1.30, 36.90)
    b = haversine_km(-1.30, 36.90, -1.29, 36.82)
    assert abs(a - b) < 1e-9


def test_estimate_minutes_minimum_one():
    assert estimate_minutes(0.01, avg_speed_kmh=30.0) == 1


def test_estimate_minutes_typical_trip():
    # 15 km at 30 km/h → 30 minutes
    assert estimate_minutes(15.0, avg_speed_kmh=30.0) == 30
