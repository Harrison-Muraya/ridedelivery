from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.core.security import get_current_user, require_role
from src.models.user import User, UserProfile, UserLocation
from src.models.requests import Request, RequestAssignment
from src.models.misc import Notification, Rating
from src.models.billing import Billing
from src.models.enums import (
    UserRole, RequestStatus, AssignmentStatus, NotificationType
)
from src.schemas.requests import AssignmentResponseRequest, AssignmentOut, RequestOut
from src.schemas.rating import CreateRatingRequest, RatingOut
from src.schemas.user import RiderAvailabilityRequest, LocationUpdate, ProfileOut, UpdateProfileRequest
from src.schemas.notifications import NotificationOut

router = APIRouter(prefix="/rider", tags=["Rider"])

_require_rider = require_role(UserRole.rider)


# ─── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await db.flush()
    return profile


# ─── Availability & Location ──────────────────────────────────────────────────

@router.post("/availability")
async def set_availability(
    payload: RiderAvailabilityRequest,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    was_unavailable = not profile.is_available
    profile.is_available = payload.is_available

    loc_result = await db.execute(
        select(UserLocation).where(UserLocation.user_id == current_user.id)
    )
    loc = loc_result.scalar_one_or_none()
    if loc:
        loc.latitude = payload.latitude
        loc.longitude = payload.longitude
    else:
        loc = UserLocation(
            user_id=current_user.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        db.add(loc)

    await db.flush()

    if payload.is_available and was_unavailable:
        from src.jobs.notification_tasks import notify_favourite_rider_online_task
        notify_favourite_rider_online_task.delay(str(current_user.id))

    return {"message": f"Availability set to {payload.is_available}"}


@router.post("/location")
async def update_location(
    payload: LocationUpdate,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    loc_result = await db.execute(
        select(UserLocation).where(UserLocation.user_id == current_user.id)
    )
    loc = loc_result.scalar_one_or_none()
    if loc:
        loc.latitude = payload.latitude
        loc.longitude = payload.longitude
        loc.heading = payload.heading
        loc.accuracy = payload.accuracy
    else:
        loc = UserLocation(
            user_id=current_user.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            heading=payload.heading,
            accuracy=payload.accuracy,
        )
        db.add(loc)
    await db.flush()
    return {"message": "Location updated"}


# ─── Assignments ──────────────────────────────────────────────────────────────

@router.get("/assignments/pending", response_model=List[AssignmentOut])
async def list_pending_assignments(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RequestAssignment)
        .where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.pending,
            )
        )
        .order_by(desc(RequestAssignment.created_at))
    )
    return result.scalars().all()


@router.get("/assignments/history", response_model=List[AssignmentOut])
async def list_assignment_history(
    assignment_status: Optional[AssignmentStatus] = Query(
        None, description="Filter by: accepted, rejected, timeout"
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    Full assignment history — accepted, rejected, and timed-out jobs.
    Useful for the rider to review what they've responded to.
    """
    stmt = select(RequestAssignment).where(
        RequestAssignment.rider_id == current_user.id
    )
    if assignment_status:
        stmt = stmt.where(RequestAssignment.assignment_status == assignment_status)
    else:
        # Exclude pending — those are in /assignments/pending
        stmt = stmt.where(
            RequestAssignment.assignment_status != AssignmentStatus.pending
        )
    stmt = stmt.order_by(desc(RequestAssignment.created_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/assignments/{assignment_id}/respond", response_model=AssignmentOut)
async def respond_to_assignment(
    assignment_id: UUID,
    payload: AssignmentResponseRequest,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RequestAssignment)
        .where(
            and_(
                RequestAssignment.id == assignment_id,
                RequestAssignment.rider_id == current_user.id,
            )
        )
        .options(selectinload(RequestAssignment.request))
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.assignment_status != AssignmentStatus.pending:
        raise HTTPException(status_code=400, detail="Assignment already responded to")

    # Revoke the timeout task so it doesn't fire after the rider already responded
    if assignment.timeout_task_id:
        from src.jobs.celery_app import celery_app
        celery_app.control.revoke(assignment.timeout_task_id, terminate=True)

    assignment.responded_at = datetime.now(timezone.utc)

    if payload.accept:
        assignment.assignment_status = AssignmentStatus.accepted
        assignment.request.request_status = RequestStatus.assigned
        assignment.request.accepted_at = datetime.now(timezone.utc)

        from src.jobs.notification_tasks import notify_customer_accepted
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == current_user.id)
        )
        profile = profile_result.scalar_one_or_none()
        rider_name = f"{profile.first_name} {profile.last_name}" if profile else "Your rider"
        notify_customer_accepted.delay(
            str(assignment.request.customer_id),
            str(assignment.request_id),
            rider_name,
        )
    else:
        assignment.assignment_status = AssignmentStatus.rejected
        assignment.rejection_reason = payload.rejection_reason

        from src.jobs.ride_tasks import dispatch_ride_search
        dispatch_ride_search.delay(str(assignment.request_id))

    await db.flush()
    return assignment


# ─── Trips ────────────────────────────────────────────────────────────────────

@router.get("/trips/active", response_model=List[RequestOut])
async def active_trips(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
                Request.request_status.in_([
                    RequestStatus.assigned,
                    RequestStatus.in_progress,
                ]),
            )
        )
    )
    return result.scalars().all()


@router.get("/trips/history", response_model=List[RequestOut])
async def trip_history(
    request_status: Optional[RequestStatus] = Query(
        None, description="Filter by: completed, cancelled"
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    All past trips the rider has been involved in.
    Defaults to completed + cancelled combined. Filter with ?request_status=completed.
    """
    stmt = (
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
            )
        )
    )
    if request_status:
        stmt = stmt.where(Request.request_status == request_status)
    else:
        stmt = stmt.where(
            Request.request_status.in_([
                RequestStatus.completed,
                RequestStatus.cancelled,
            ])
        )
    stmt = stmt.order_by(desc(Request.created_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/trips/{request_id}", response_model=RequestOut)
async def get_trip_detail(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """Full detail for any single trip the rider is/was assigned to."""
    result = await db.execute(
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                Request.id == request_id,
                RequestAssignment.rider_id == current_user.id,
            )
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Trip not found")
    return req


@router.post("/trips/{request_id}/arrived", response_model=RequestOut)
async def mark_arrived_at_pickup(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    Rider has reached the pickup location.
    Notifies the customer so they know to come out.
    The request stays in 'assigned' status — call /start once the customer boards.
    """
    req = await _get_rider_request(
        db, request_id, current_user.id, RequestStatus.assigned
    )

    notif = Notification(
        user_id=req.customer_id,
        notification_type=NotificationType.rider_arrived,
        title="Rider Has Arrived",
        body="Your rider is at the pickup location. Please come out!",
        data=str({"request_id": str(request_id)}),
    )
    db.add(notif)
    await db.flush()
    return req


@router.post("/trips/{request_id}/start", response_model=RequestOut)
async def start_trip(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    req = await _get_rider_request(
        db, request_id, current_user.id, RequestStatus.assigned
    )
    req.request_status = RequestStatus.in_progress
    req.started_at = datetime.now(timezone.utc)

    notif = Notification(
        user_id=req.customer_id,
        notification_type=NotificationType.trip_started,
        title="Trip Started",
        body="Your rider has started the trip. Hang tight!",
        data=str({"request_id": str(request_id)}),
    )
    db.add(notif)
    await db.flush()
    return req


@router.post("/trips/{request_id}/complete", response_model=RequestOut)
async def complete_trip(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    req = await _get_rider_request(
        db, request_id, current_user.id, RequestStatus.in_progress
    )
    req.request_status = RequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.final_fare = req.estimated_fare
    await db.flush()

    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.total_trips += 1

    from src.jobs.payment_tasks import create_billing_record
    from src.jobs.notification_tasks import notify_trip_completed
    create_billing_record.delay(str(request_id), str(current_user.id))
    notify_trip_completed.delay(
        str(req.customer_id), str(current_user.id), str(request_id), str(req.final_fare)
    )
    return req


@router.post("/trips/{request_id}/cancel")
async def cancel_trip(
    request_id: UUID,
    reason: str = "Rider cancelled",
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    Rider cancels an accepted trip that has NOT yet started.
    Once a trip is in_progress it cannot be cancelled by the rider —
    they must complete it.
    Re-opens the request so the system can find another rider.
    """
    result = await db.execute(
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                Request.id == request_id,
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
                # Only allow cancel before trip starts
                Request.request_status == RequestStatus.assigned,
            )
        )
        .options(selectinload(Request.assignments))
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=404,
            detail="Trip not found, already started, or not assigned to you",
        )

    # Mark the current assignment as rejected so dispatch skips this rider next time
    accepted_assignment = next(
        (a for a in req.assignments
         if a.rider_id == current_user.id and a.assignment_status == AssignmentStatus.accepted),
        None,
    )
    if accepted_assignment:
        accepted_assignment.assignment_status = AssignmentStatus.rejected
        accepted_assignment.rejection_reason = reason
        accepted_assignment.responded_at = datetime.now(timezone.utc)

    # Re-open the request and search for the next available rider
    req.request_status = RequestStatus.searching
    await db.flush()

    # Notify customer their rider cancelled
    notif = Notification(
        user_id=req.customer_id,
        notification_type=NotificationType.new_request,
        title="Rider Cancelled",
        body="Your rider had to cancel. We are finding you another rider now.",
        data=str({"request_id": str(request_id)}),
    )
    db.add(notif)
    await db.flush()

    from src.jobs.ride_tasks import dispatch_ride_search
    dispatch_ride_search.delay(str(request_id))

    return {
        "message": "Trip cancelled. We are searching for another rider for the customer.",
        "request_id": str(request_id),
    }


async def _get_rider_request(
    db: AsyncSession,
    request_id: UUID,
    rider_id: UUID,
    expected_status: RequestStatus,
) -> Request:
    result = await db.execute(
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                Request.id == request_id,
                RequestAssignment.rider_id == rider_id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
                Request.request_status == expected_status,
            )
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=404,
            detail=f"Request not found or not in expected state ({expected_status})",
        )
    return req


# ─── Earnings & Wallet ────────────────────────────────────────────────────────

@router.get("/earnings/summary")
async def earnings_summary(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    Lifetime earnings breakdown: total earned, platform commission taken,
    trips completed, and current wallet balance.
    """
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    billing_result = await db.execute(
        select(
            func.sum(Billing.rider_earnings).label("total_earned"),
            func.sum(Billing.total_amount).label("total_billed"),
            func.count(Billing.id).label("paid_trips"),
        ).where(Billing.rider_id == current_user.id)
    )
    row = billing_result.one()

    total_billed = float(row.total_billed or 0)
    total_earned = float(row.total_earned or 0)
    commission_taken = total_billed - total_earned

    return {
        "wallet_balance_kes": float(profile.wallet_balance),
        "total_earned_kes": round(total_earned, 2),
        "total_billed_kes": round(total_billed, 2),
        "platform_commission_kes": round(commission_taken, 2),
        "paid_trips": row.paid_trips,
        "total_trips_completed": profile.total_trips,
    }


@router.get("/earnings/history")
async def earnings_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """Per-trip earnings history, most recent first."""
    result = await db.execute(
        select(Billing)
        .where(Billing.rider_id == current_user.id)
        .order_by(desc(Billing.created_at))
        .limit(limit)
    )
    billings = result.scalars().all()
    return [
        {
            "billing_id": str(b.id),
            "request_id": str(b.request_id),
            "total_fare_kes": float(b.total_amount),
            "rider_earnings_kes": float(b.rider_earnings or 0),
            "billing_status": b.billing_status,
            "paid_at": b.paid_at,
            "created_at": b.created_at,
        }
        for b in billings
    ]


# ─── Ratings ──────────────────────────────────────────────────────────────────

@router.post("/ratings", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
async def submit_rating(
    payload: CreateRatingRequest,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """Rate the customer after a completed trip."""
    result = await db.execute(
        select(RequestAssignment).where(
            and_(
                RequestAssignment.request_id == payload.request_id,
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You were not the rider for this trip")

    dup = await db.execute(
        select(Rating).where(
            and_(
                Rating.request_id == payload.request_id,
                Rating.rater_id == current_user.id,
            )
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already rated this trip")

    rating = Rating(
        request_id=payload.request_id,
        rater_id=current_user.id,
        ratee_id=payload.ratee_id,
        score=payload.score,
        comment=payload.comment,
    )
    db.add(rating)
    await db.flush()

    avg_result = await db.execute(
        select(func.avg(Rating.score), func.count(Rating.id))
        .where(Rating.ratee_id == payload.ratee_id)
    )
    avg, cnt = avg_result.one()
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == payload.ratee_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.rating_avg = float(avg or 0)
        profile.rating_count = cnt

    return rating


@router.get("/ratings/received", response_model=List[RatingOut])
async def ratings_received(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """All ratings customers have given to this rider."""
    result = await db.execute(
        select(Rating)
        .where(Rating.ratee_id == current_user.id)
        .order_by(desc(Rating.created_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/ratings/given", response_model=List[RatingOut])
async def ratings_given(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """All ratings this rider has submitted for customers."""
    result = await db.execute(
        select(Rating)
        .where(Rating.rater_id == current_user.id)
        .order_by(desc(Rating.created_at))
        .limit(limit)
    )
    return result.scalars().all()


# ─── Notifications ────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=List[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    result = await db.execute(
        stmt.order_by(desc(Notification.created_at)).limit(50)
    )
    return result.scalars().all()


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
            )
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    await db.flush()
    return {"message": "Marked as read"}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """Mark every unread notification as read in one call."""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False,
            )
        )
    )
    now = datetime.now(timezone.utc)
    count = 0
    for notif in result.scalars().all():
        notif.is_read = True
        notif.read_at = now
        count += 1
    await db.flush()
    return {"message": f"{count} notification(s) marked as read"}


# ─── Dashboard (rider home screen summary) ───────────────────────────────────

@router.get("/dashboard")
async def rider_dashboard(
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    """
    Single endpoint for the rider home screen.
    Returns availability, wallet balance, today's trips, pending assignments,
    and unread notification count — all in one call.
    """
    from datetime import date

    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Pending assignments count
    pending_result = await db.execute(
        select(func.count(RequestAssignment.id)).where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.pending,
            )
        )
    )
    pending_count = pending_result.scalar()

    # Unread notifications count
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False,
            )
        )
    )
    unread_count = unread_result.scalar()

    # Trips completed today
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    today_trips_result = await db.execute(
        select(func.count(Request.id))
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
                Request.request_status == RequestStatus.completed,
                Request.completed_at >= today_start,
            )
        )
    )
    today_trips = today_trips_result.scalar()

    # Today's earnings
    today_earnings_result = await db.execute(
        select(func.sum(Billing.rider_earnings)).where(
            and_(
                Billing.rider_id == current_user.id,
                Billing.paid_at >= today_start,
            )
        )
    )
    today_earnings = float(today_earnings_result.scalar() or 0)

    # Active trip if any
    active_result = await db.execute(
        select(Request)
        .join(RequestAssignment, RequestAssignment.request_id == Request.id)
        .where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.accepted,
                Request.request_status.in_([
                    RequestStatus.assigned,
                    RequestStatus.in_progress,
                ]),
            )
        )
        .limit(1)
    )
    active_trip = active_result.scalar_one_or_none()

    return {
        "rider_name": f"{profile.first_name} {profile.last_name}",
        "is_available": profile.is_available,
        "wallet_balance_kes": float(profile.wallet_balance),
        "rating_avg": round(profile.rating_avg, 2),
        "total_trips": profile.total_trips,
        "today_trips_completed": today_trips,
        "today_earnings_kes": round(today_earnings, 2),
        "pending_assignments": pending_count,
        "unread_notifications": unread_count,
        "active_trip": {
            "request_id": str(active_trip.id),
            "status": active_trip.request_status,
            "pickup_address": active_trip.pickup_address,
            "dropoff_address": active_trip.dropoff_address,
        } if active_trip else None,
    }