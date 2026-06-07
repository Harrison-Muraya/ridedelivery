from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.core.security import require_role
from src.models.user import User, UserRoleMap, UserProfile
from src.models.requests import Request, RequestAssignment
from src.models.misc import PricingConfig, SystemLog, Notification
from src.models.billing import Billing
from src.models.enums import (
    UserRole, RequestStatus, AssignmentStatus, NotificationType
)
from src.schemas.admin import UpdatePricingRequest, AdminAssignRiderRequest, PricingConfigOut
from src.schemas.requests import RequestOut, AssignmentOut
from src.schemas.user import UserResponse

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


@router.delete("/pricing/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing(
    config_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a specific pricing config (soft delete)."""
    result = await db.execute(select(PricingConfig).where(PricingConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Pricing config not found")
    config.is_active = False
    log = SystemLog(
        actor_id=current_user.id,
        event_type="pricing_deactivated",
        entity="PricingConfig",
        entity_id=str(config_id),
    )
    db.add(log)
    await db.flush()


# ─── Requests (all status views) ─────────────────────────────────────────────

@router.get("/requests", response_model=List[RequestOut])
async def list_requests(
    request_status: Optional[RequestStatus] = Query(
        None,
        description="Filter by status: pending, searching, assigned, in_progress, completed, cancelled, admin_escalated",
    ),
    from_date: Optional[date] = Query(None, description="Filter from this date (inclusive), e.g. 2024-01-01"),
    to_date: Optional[date] = Query(None, description="Filter up to this date (inclusive)"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List all requests with optional filters.
    Use ?request_status=active shorthand as well as any RequestStatus value.
    """
    stmt = select(Request)

    if request_status:
        stmt = stmt.where(Request.request_status == request_status)

    if from_date:
        stmt = stmt.where(Request.created_at >= datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc))
    if to_date:
        # include the full to_date day
        from datetime import timedelta
        next_day = datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc) + timedelta(days=1)
        stmt = stmt.where(Request.created_at < next_day)

    stmt = stmt.order_by(desc(Request.created_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/requests/active", response_model=List[RequestOut])
async def list_active_requests(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Requests currently assigned to a rider or in progress."""
    result = await db.execute(
        select(Request)
        .where(
            Request.request_status.in_([
                RequestStatus.assigned,
                RequestStatus.in_progress,
                RequestStatus.searching,
            ])
        )
        .order_by(desc(Request.created_at))
        .limit(100)
    )
    return result.scalars().all()


@router.get("/requests/completed", response_model=List[RequestOut])
async def list_completed_requests(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All completed rides and deliveries."""
    stmt = select(Request).where(Request.request_status == RequestStatus.completed)

    if from_date:
        stmt = stmt.where(Request.completed_at >= datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc))
    if to_date:
        from datetime import timedelta
        next_day = datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc) + timedelta(days=1)
        stmt = stmt.where(Request.completed_at < next_day)

    stmt = stmt.order_by(desc(Request.completed_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/requests/cancelled", response_model=List[RequestOut])
async def list_cancelled_requests(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All cancelled requests."""
    result = await db.execute(
        select(Request)
        .where(Request.request_status == RequestStatus.cancelled)
        .order_by(desc(Request.cancelled_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/requests/{request_id}", response_model=RequestOut)
async def get_request_detail(
    request_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Full detail for any single request."""
    result = await db.execute(
        select(Request).where(Request.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


# ─── Escalated Requests ───────────────────────────────────────────────────────

@router.get("/escalated-requests", response_model=List[RequestOut])
async def list_escalated(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request)
        .where(Request.request_status == RequestStatus.admin_escalated)
        .order_by(desc(Request.created_at))
    )
    return result.scalars().all()


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


# ─── Users & Riders ───────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    role: Optional[str] = None,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    id_stmt = select(User.id)
    if role:
        role_subq = select(UserRoleMap.user_id).where(UserRoleMap.role == role)
        id_stmt = id_stmt.where(User.id.in_(role_subq))
    id_stmt = id_stmt.limit(100)

    id_result = await db.execute(id_stmt)
    user_ids = [row[0] for row in id_result.all()]
    if not user_ids:
        return []

    stmt = (
        select(User)
        .where(User.id.in_(user_ids))
        .options(
            selectinload(User.profile),
            selectinload(User.roles),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_detail(
    user_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Full profile for any user, including their roles and profile data."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.profile), selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


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


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reverse a deactivation — allows the user to log in again."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")
    user.is_active = True
    log = SystemLog(
        actor_id=current_user.id,
        event_type="user_reactivated",
        entity="User",
        entity_id=str(user_id),
    )
    db.add(log)
    await db.flush()
    return {"message": "User reactivated"}


@router.patch("/riders/{rider_id}/availability")
async def set_rider_availability(
    rider_id: UUID,
    is_available: bool,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually toggle a rider's availability.
    Useful when a rider is stuck online after an incident.
    """
    result = await db.execute(
        select(UserProfile)
        .join(UserRoleMap, UserRoleMap.user_id == UserProfile.user_id)
        .where(
            and_(
                UserProfile.user_id == rider_id,
                UserRoleMap.role == UserRole.rider,
            )
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Rider not found")
    profile.is_available = is_available
    log = SystemLog(
        actor_id=current_user.id,
        event_type="admin_set_rider_availability",
        entity="UserProfile",
        entity_id=str(rider_id),
        detail=str({"is_available": is_available}),
    )
    db.add(log)
    await db.flush()
    return {"message": f"Rider availability set to {is_available}"}


@router.get("/riders/{rider_id}/active-assignment")
async def get_rider_active_assignment(
    rider_id: UUID,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Check what trip a rider is currently on, if any."""
    result = await db.execute(
        select(RequestAssignment)
        .options(selectinload(RequestAssignment.request))
        .where(
            and_(
                RequestAssignment.rider_id == rider_id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
            )
        )
        .join(Request, Request.id == RequestAssignment.request_id)
        .where(
            Request.request_status.in_([
                RequestStatus.assigned,
                RequestStatus.in_progress,
            ])
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        return {"active_assignment": None}
    return {
        "active_assignment": {
            "assignment_id": str(assignment.id),
            "request_id": str(assignment.request_id),
            "request_status": assignment.request.request_status,
            "started_at": assignment.request.started_at,
            "accepted_at": assignment.request.accepted_at,
        }
    }


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
    active = (await db.execute(
        select(func.count(Request.id)).where(
            Request.request_status.in_([RequestStatus.assigned, RequestStatus.in_progress])
        )
    )).scalar()
    cancelled = (await db.execute(
        select(func.count(Request.id)).where(Request.request_status == RequestStatus.cancelled)
    )).scalar()
    total_revenue = (await db.execute(
        select(func.sum(Billing.total_amount))
    )).scalar() or 0

    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "active_trips": active,
        "completed_trips": completed,
        "cancelled_trips": cancelled,
        "escalated_requests": escalated,
        "total_revenue_kes": float(total_revenue),
    }


@router.get("/stats/revenue")
async def revenue_stats(
    from_date: Optional[date] = Query(None, description="Start date, e.g. 2024-01-01"),
    to_date: Optional[date] = Query(None, description="End date, e.g. 2024-01-31"),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Revenue breakdown: total collected, platform commission, rider earnings.
    Optionally scoped to a date range via from_date / to_date.
    """
    from src.models.enums import BillingStatus
    from decimal import Decimal

    stmt = select(
        func.sum(Billing.total_amount).label("total_revenue"),
        func.sum(Billing.rider_earnings).label("total_rider_earnings"),
        func.count(Billing.id).label("paid_trips"),
    ).where(Billing.billing_status == BillingStatus.paid)

    if from_date:
        stmt = stmt.where(Billing.paid_at >= datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc))
    if to_date:
        from datetime import timedelta
        next_day = datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc) + timedelta(days=1)
        stmt = stmt.where(Billing.paid_at < next_day)

    row = (await db.execute(stmt)).one()
    total_revenue = float(row.total_revenue or 0)
    rider_earnings = float(row.total_rider_earnings or 0)
    commission = total_revenue - rider_earnings

    return {
        "from_date": str(from_date) if from_date else None,
        "to_date": str(to_date) if to_date else None,
        "paid_trips": row.paid_trips,
        "total_revenue_kes": round(total_revenue, 2),
        "platform_commission_kes": round(commission, 2),
        "rider_earnings_kes": round(rider_earnings, 2),
    }


@router.get("/stats/riders")
async def rider_stats(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top riders ranked by completed trips with their earnings and rating."""
    result = await db.execute(
        select(
            UserProfile.user_id,
            UserProfile.first_name,
            UserProfile.last_name,
            UserProfile.total_trips,
            UserProfile.rating_avg,
            UserProfile.rating_count,
            UserProfile.wallet_balance,
            UserProfile.is_available,
        )
        .join(UserRoleMap, UserRoleMap.user_id == UserProfile.user_id)
        .where(UserRoleMap.role == UserRole.rider)
        .order_by(desc(UserProfile.total_trips))
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "rider_id": str(r.user_id),
            "name": f"{r.first_name} {r.last_name}",
            "total_trips": r.total_trips,
            "rating_avg": round(r.rating_avg, 2),
            "rating_count": r.rating_count,
            "wallet_balance_kes": float(r.wallet_balance),
            "is_available": r.is_available,
        }
        for r in rows
    ]


# ─── System Logs ─────────────────────────────────────────────────────────────

@router.get("/logs")
async def list_system_logs(
    event_type: Optional[str] = Query(None, description="e.g. pricing_updated, user_deactivated"),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Audit trail of admin actions and system events."""
    stmt = select(SystemLog)
    if event_type:
        stmt = stmt.where(SystemLog.event_type == event_type)
    stmt = stmt.order_by(desc(SystemLog.created_at)).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "actor_id": str(log.actor_id) if log.actor_id else None,
            "event_type": log.event_type,
            "entity": log.entity,
            "entity_id": log.entity_id,
            "detail": log.detail,
            "created_at": log.created_at,
        }
        for log in logs
    ]