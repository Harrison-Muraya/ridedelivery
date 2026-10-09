from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.services.assignment_config import (
    AssignmentSettings,
    get_assignment_settings,
    get_assignment_settings_sync,
    upsert_assignment_settings,
)


@pytest.mark.asyncio
async def test_get_assignment_settings_returns_env_defaults(monkeypatch):
    monkeypatch.setattr(
        "src.services.assignment_config.settings.RIDER_RESPONSE_TIMEOUT_SECONDS",
        300,
    )
    monkeypatch.setattr(
        "src.services.assignment_config.settings.MAX_SEARCH_RADIUS_KM",
        10.0,
    )
    monkeypatch.setattr(
        "src.services.assignment_config.settings.INITIAL_SEARCH_RADIUS_KM",
        3.0,
    )
    monkeypatch.setattr(
        "src.services.assignment_config.settings.MAX_ASSIGNMENT_ATTEMPTS",
        5,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result_mock

    cfg = await get_assignment_settings(db)
    assert cfg == AssignmentSettings(
        rider_response_timeout_seconds=300,
        max_search_radius_km=10.0,
        initial_search_radius_km=3.0,
        max_assignment_attempts=5,
        source="defaults",
    )


def test_get_assignment_settings_sync_uses_db_row():
    row = SimpleNamespace(
        id=uuid4(),
        rider_response_timeout_seconds=120,
        max_search_radius_km=15.0,
        initial_search_radius_km=4.0,
        max_assignment_attempts=7,
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.first.return_value = row
    db = MagicMock()
    db.query.return_value = query

    cfg = get_assignment_settings_sync(db)
    assert cfg.source == "database"
    assert cfg.rider_response_timeout_seconds == 120
    assert cfg.max_assignment_attempts == 7


@pytest.mark.asyncio
async def test_upsert_creates_row_when_missing():
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result_mock

    row = await upsert_assignment_settings(
        db,
        rider_response_timeout_seconds=180,
        max_search_radius_km=12.0,
        initial_search_radius_km=2.5,
        max_assignment_attempts=4,
        updated_by=uuid4(),
    )
    db.add.assert_called_once()
    assert row.rider_response_timeout_seconds == 180
    assert row.max_search_radius_km == 12.0
