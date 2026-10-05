"""Load rider-assignment settings from DB, falling back to env defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.config import settings
from src.models.misc import AssignmentConfig


@dataclass(frozen=True)
class AssignmentSettings:
    rider_response_timeout_seconds: int
    max_search_radius_km: float
    initial_search_radius_km: float
    max_assignment_attempts: int
    id: Optional[UUID] = None
    source: str = "defaults"  # "defaults" | "database"


def _defaults() -> AssignmentSettings:
    return AssignmentSettings(
        rider_response_timeout_seconds=settings.RIDER_RESPONSE_TIMEOUT_SECONDS,
        max_search_radius_km=settings.MAX_SEARCH_RADIUS_KM,
        initial_search_radius_km=settings.INITIAL_SEARCH_RADIUS_KM,
        max_assignment_attempts=settings.MAX_ASSIGNMENT_ATTEMPTS,
        source="defaults",
    )


def _from_row(row: AssignmentConfig) -> AssignmentSettings:
    return AssignmentSettings(
        rider_response_timeout_seconds=int(row.rider_response_timeout_seconds),
        max_search_radius_km=float(row.max_search_radius_km),
        initial_search_radius_km=float(row.initial_search_radius_km),
        max_assignment_attempts=int(row.max_assignment_attempts),
        id=row.id,
        source="database",
    )


async def get_assignment_settings(db: AsyncSession) -> AssignmentSettings:
    result = await db.execute(
        select(AssignmentConfig)
        .where(AssignmentConfig.is_active.is_(True))
        .order_by(AssignmentConfig.updated_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return _from_row(row) if row else _defaults()


def get_assignment_settings_sync(db: Session) -> AssignmentSettings:
    row = (
        db.query(AssignmentConfig)
        .filter(AssignmentConfig.is_active.is_(True))
        .order_by(AssignmentConfig.updated_at.desc())
        .first()
    )
    return _from_row(row) if row else _defaults()


async def upsert_assignment_settings(
    db: AsyncSession,
    *,
    rider_response_timeout_seconds: int,
    max_search_radius_km: float,
    initial_search_radius_km: float,
    max_assignment_attempts: int,
    updated_by: Optional[UUID] = None,
) -> AssignmentConfig:
    result = await db.execute(
        select(AssignmentConfig)
        .where(AssignmentConfig.is_active.is_(True))
        .order_by(AssignmentConfig.updated_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row:
        row.rider_response_timeout_seconds = rider_response_timeout_seconds
        row.max_search_radius_km = max_search_radius_km
        row.initial_search_radius_km = initial_search_radius_km
        row.max_assignment_attempts = max_assignment_attempts
        row.updated_by = updated_by
        await db.flush()
        return row

    row = AssignmentConfig(
        rider_response_timeout_seconds=rider_response_timeout_seconds,
        max_search_radius_km=max_search_radius_km,
        initial_search_radius_km=initial_search_radius_km,
        max_assignment_attempts=max_assignment_attempts,
        updated_by=updated_by,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    return row
