from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import routing


@pytest.mark.asyncio
async def test_road_route_uses_osrm_distance_and_duration(monkeypatch):
    monkeypatch.setattr(routing.settings, "ROUTING_ENABLED", True)
    monkeypatch.setattr(routing.settings, "OSRM_BASE_URL", "https://router.example")
    monkeypatch.setattr(routing.settings, "OSRM_TIMEOUT_SECONDS", 5.0)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "code": "Ok",
        "routes": [{"distance": 31200.0, "duration": 2460.0}],
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_resp

    with patch("src.services.routing.httpx.AsyncClient", return_value=mock_client):
        result = await routing.road_route(-1.286389, 36.817223, -1.473056, 36.956944)

    assert result["source"] == "osrm"
    assert result["distance_km"] == 31.2
    assert result["duration_minutes"] == 41
    # OSRM URL must use lon,lat order
    called_url = mock_client.get.await_args.args[0]
    assert "36.817223,-1.286389;36.956944,-1.473056" in called_url


@pytest.mark.asyncio
async def test_road_route_falls_back_to_haversine(monkeypatch):
    monkeypatch.setattr(routing.settings, "ROUTING_ENABLED", True)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.side_effect = Exception("network down")

    with patch("src.services.routing.httpx.AsyncClient", return_value=mock_client):
        result = await routing.road_route(-1.286389, 36.817223, -1.473056, 36.956944)

    assert result["source"] == "haversine"
    assert 24.0 < result["distance_km"] < 30.0
    assert result["duration_minutes"] >= 1


@pytest.mark.asyncio
async def test_road_route_can_disable_routing(monkeypatch):
    monkeypatch.setattr(routing.settings, "ROUTING_ENABLED", False)
    result = await routing.road_route(-1.286389, 36.817223, -1.473056, 36.956944)
    assert result["source"] == "haversine"
