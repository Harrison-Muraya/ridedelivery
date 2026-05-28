from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.core.security import require_role
from src.models.user import User, UserRoleMap, UserProfile
from src.models.requests import Request, RequestAssignment
from src.models.misc import PricingConfig, SystemLog
from src.models.billing import Billing
from src.models.enums import (
    UserRole, RequestStatus, AssignmentStatus, NotificationType
)
from src.schemas.admin import UpdatePricingRequest, AdminAssignRiderRequest, PricingConfigOut
from src.schemas.requests import RequestOut, AssignmentOut
from src.schemas.userProfile import UserOut

router = APIRouter(prefix="/admin", tags=["Admin"])

_require_admin = require_role(UserRole.admin)


# ─── Pricing ──────────────────────────────────────────────────────────────────

@router.get("/pricing", response_model=List[PricingConfigOut])
async def list_pricing(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PricingConfig).order_by(PricingConfig.request_type))
    return result.scalars().all()


@router.post("/pricing", response_model=PricingConfigOut, status_code=status.HTTP_201_CREATED)
async def upsert_pricing(
    payload: UpdatePricingRequest,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Deactivate existing configs for this type/vehicle
    result = await db.execute(
        select(PricingConfig).where(
            and_(
                PricingConfig.request_type == payload.request_type,
                PricingConfig.vehicle_type == payload.vehicle_type,
            )
        )
    )
    for old in result.scalars().all():
        old.is_active = False

    config = PricingConfig(
        request_type=payload.request_type,
        vehicle_type=payload.vehicle_type,
        base_fare=payload.base_fare,
        per_km_rate=payload.per_km_rate,
        per_minute_rate=payload.per_minute_rate,
        minimum_fare=payload.minimum_fare,
        surge_multiplier=payload.surge_multiplier,
        updated_by=current_user.id,
    )
    db.add(config)

    log = SystemLog(
        actor_id=current_user.id,
        event_type="pricing_updated",
        entity="PricingConfig",
        detail=str(payload.model_dump()),
    )
    db.add(log)
    await db.flush()

    return config


# ─── Manual Rider Assignment ───────────────────────────────────────────────────

@router.post("/assign-rider", response_model=AssignmentOut)
async def admin_assign_rider(
    payload: AdminAssignRiderRequest,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    req_result = await db.execute(
        select(Request)
        .where(Request.id == payload.request_id)
        .options(selectinload(Request.assignments))
    )
    req = req_result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.request_status in (RequestStatus.completed, RequestStatus.cancelled):
        raise HTTPException(status_code=400, detail="Request is in a terminal state")

    # Verify rider exists
    rider_result = await db.execute(
        select(UserRoleMap).where(
            and_(
                UserRoleMap.user_id == payload.rider_id,
                UserRoleMap.role == UserRole.rider,
            )
        )
    )
    if not rider_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Rider not found")

    attempt = len(req.assignments) + 1
    assignment = RequestAssignment(
        request_id=req.id,
        rider_id=payload.rider_id,
        attempt_number=attempt,
        assignment_status=AssignmentStatus.accepted,
    )
    db.add(assignment)
    req.request_status = RequestStatus.assigned

    from src.models.misc import Notification
    notif = Notification(
        user_id=payload.rider_id,
        notification_type=NotificationType.new_request,
        title="Admin Assigned You a Job",
        body="An admin has assigned you a ride/delivery. Please proceed.",
        data=str({"request_id": str(req.id)}),
    )
    db.add(notif)

    log = SystemLog(
        actor_id=current_user.id,
        event_type="admin_manual_assign",
        entity="RequestAssignment",
        detail=str({"request_id": str(req.id), "rider_id": str(payload.rider_id)}),
    )
    db.add(log)
    await db.flush()
    return assignment


# ─── Escalated Requests ───────────────────────────────────────────────────────

@router.get("/escalated-requests", response_model=List[RequestOut])
async def list_escalated(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request)
        .where(Request.request_status == RequestStatus.admin_escalated)
        .order_by(Request.created_at.desc())
    )
    return result.scalars().all()


# ─── Users & Riders ───────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserOut])
async def list_users(
    role: str = None,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).options(selectinload(User.profile))
    if role:
        stmt = stmt.join(UserRoleMap).where(UserRoleMap.role == role)
    result = await db.execute(stmt.limit(100))
    return result.scalars().unique().all()


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    log = SystemLog(
        actor_id=current_user.id,
        event_type="user_deactivated",
        entity="User",
        entity_id=str(user_id),
    )
    db.add(log)
    await db.flush()
    return {"message": "User deactivated"}


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@router.get("/stats")
async def dashboard_stats(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_requests = (await db.execute(select(func.count(Request.id)))).scalar()
    completed = (await db.execute(
        select(func.count(Request.id)).where(Request.request_status == RequestStatus.completed)
    )).scalar()
    escalated = (await db.execute(
        select(func.count(Request.id)).where(Request.request_status == RequestStatus.admin_escalated)
    )).scalar()
    total_revenue = (await db.execute(
        select(func.sum(Billing.total_amount))
    )).scalar() or 0

    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "completed_trips": completed,
        "escalated_requests": escalated,
        "total_revenue_kes": float(total_revenue),
    }
