from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.core.security import get_current_user, require_role
from src.models.user import User, UserProfile, UserLocation
from src.models.requests import Request, RequestAssignment
from src.models.misc import Notification
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
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
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
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
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
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    was_unavailable = not profile.is_available
    profile.is_available = payload.is_available

    # Update location
    loc_result = await db.execute(select(UserLocation).where(UserLocation.user_id == current_user.id))
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

    # If rider just went online, notify their customers asynchronously
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
    loc_result = await db.execute(select(UserLocation).where(UserLocation.user_id == current_user.id))
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
        select(RequestAssignment).where(
            and_(
                RequestAssignment.rider_id == current_user.id,
                RequestAssignment.assignment_status == AssignmentStatus.pending,
            )
        ).order_by(RequestAssignment.created_at.desc())
    )
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

    # Revoke timeout task
    if assignment.timeout_task_id:
        from src.jobs.celery_app import celery_app
        celery_app.control.revoke(assignment.timeout_task_id, terminate=True)

    assignment.responded_at = datetime.now(timezone.utc)

    if payload.accept:
        assignment.assignment_status = AssignmentStatus.accepted
        assignment.request.request_status = RequestStatus.assigned
        assignment.request.accepted_at = datetime.now(timezone.utc)

        # Notify customer
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

        # Search for next rider
        from src.jobs.ride_tasks import dispatch_ride_search
        dispatch_ride_search.delay(str(assignment.request_id))

    await db.flush()
    return assignment


# ─── Active Trip Management ───────────────────────────────────────────────────

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
                Request.request_status.in_([RequestStatus.assigned, RequestStatus.in_progress]),
            )
        )
    )
    return result.scalars().all()


@router.post("/trips/{request_id}/start", response_model=RequestOut)
async def start_trip(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    req = await _get_rider_request(db, request_id, current_user.id, RequestStatus.assigned)
    req.request_status = RequestStatus.in_progress
    req.started_at = datetime.now(timezone.utc)
    await db.flush()

    notif = Notification(
        user_id=req.customer_id,
        notification_type=NotificationType.trip_started,
        title="Trip Started",
        body="Your rider has started the trip. Hang tight!",
        data=str({"request_id": str(request_id)}),
    )
    db.add(notif)
    return req


@router.post("/trips/{request_id}/complete", response_model=RequestOut)
async def complete_trip(
    request_id: UUID,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    req = await _get_rider_request(db, request_id, current_user.id, RequestStatus.in_progress)
    req.request_status = RequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.final_fare = req.estimated_fare
    await db.flush()

    # Update rider trip count
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.total_trips += 1

    # Create billing + notify async
    from src.jobs.payment_tasks import create_billing_record
    from src.jobs.notification_tasks import notify_trip_completed
    create_billing_record.delay(str(request_id), str(current_user.id))
    notify_trip_completed.delay(
        str(req.customer_id), str(current_user.id), str(request_id), str(req.final_fare)
    )
    return req


async def _get_rider_request(
    db: AsyncSession, request_id: UUID, rider_id: UUID, expected_status: RequestStatus
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
        raise HTTPException(status_code=404, detail=f"Request not found or not in {expected_status} state")
    return req


# ─── Ratings ──────────────────────────────────────────────────────────────────

@router.post("/ratings", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
async def submit_rating(
    payload: CreateRatingRequest,
    current_user: User = Depends(_require_rider),
    db: AsyncSession = Depends(get_db),
):
    from src.models.misc import Rating
    from sqlalchemy import func

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
            and_(Rating.request_id == payload.request_id, Rating.rater_id == current_user.id)
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

    # Update ratee avg
    avg_result = await db.execute(
        select(func.avg(Rating.score), func.count(Rating.id)).where(Rating.ratee_id == payload.ratee_id)
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
    result = await db.execute(stmt.order_by(Notification.created_at.desc()).limit(50))
    return result.scalars().all()
