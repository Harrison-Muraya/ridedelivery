from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.core.security import get_current_user, require_role
from src.models.user import User, UserProfile, FavoriteRider
from src.models.requests import Request, RequestAssignment
from src.models.misc import Rating, Notification
from src.models.billing import Billing, Transaction
from src.models.enums import (
    UserRole, RequestStatus, AssignmentStatus, PaymentMethod, TransactionStatus
)
from src.schemas.requests import CreateRideRequest, RequestOut, FareEstimateOut
from src.schemas.rating import CreateRatingRequest, RatingOut
from src.schemas.billing import BillingOut
from src.schemas.payments import InitiatePaymentRequest, TransactionOut
from src.schemas.notifications import NotificationOut
from src.schemas.user import UpdateProfileRequest, ProfileOut, LocationUpdate, RiderAvailabilityRequest
from src.services.distance import haversine_km, estimate_minutes
from src.services.fare import calculate_fare
from src.services import mpesa as mpesa_service

router = APIRouter(prefix="/customer", tags=["Customer"])

_require_customer = require_role(UserRole.customer)


# ─── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(_require_customer),
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
    current_user: User = Depends(_require_customer),
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


# ─── Fare Estimate ────────────────────────────────────────────────────────────

@router.get("/fare-estimate", response_model=FareEstimateOut)
async def fare_estimate(
    pickup_lat: float,
    pickup_lon: float,
    dropoff_lat: float,
    dropoff_lon: float,
    request_type: str = "ride",
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    from src.models.enums import RequestType
    r_type = RequestType(request_type)
    dist = haversine_km(pickup_lat, pickup_lon, dropoff_lat, dropoff_lon)
    breakdown = await calculate_fare(db, r_type, dist)
    return FareEstimateOut(
        distance_km=breakdown["distance_km"],
        estimated_minutes=breakdown["estimated_minutes"],
        estimated_fare=breakdown["total_amount"],
        breakdown=breakdown,
    )


# ─── Requests ─────────────────────────────────────────────────────────────────

@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: CreateRideRequest,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    dist = haversine_km(
        payload.pickup_latitude, payload.pickup_longitude,
        payload.dropoff_latitude, payload.dropoff_longitude,
    )
    breakdown = await calculate_fare(db, payload.request_type, dist)

    req = Request(
        customer_id=current_user.id,
        preferred_rider_id=payload.preferred_rider_id,
        request_type=payload.request_type,
        request_status=RequestStatus.pending,
        pickup_latitude=payload.pickup_latitude,
        pickup_longitude=payload.pickup_longitude,
        pickup_address=payload.pickup_address,
        dropoff_latitude=payload.dropoff_latitude,
        dropoff_longitude=payload.dropoff_longitude,
        dropoff_address=payload.dropoff_address,
        package_description=payload.package_description,
        recipient_name=payload.recipient_name,
        recipient_phone=payload.recipient_phone,
        distance_km=dist,
        estimated_minutes=breakdown["estimated_minutes"],
        estimated_fare=breakdown["total_amount"],
    )
    db.add(req)
    await db.flush()

    # Kick off rider search asynchronously
    from src.jobs.ride_tasks import dispatch_ride_search
    dispatch_ride_search.delay(str(req.id))

    return req


@router.get("/requests", response_model=List[RequestOut])
async def list_requests(
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request)
        .where(Request.customer_id == current_user.id)
        .order_by(Request.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/requests/{request_id}", response_model=RequestOut)
async def get_request(
    request_id: UUID,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request).where(
            and_(Request.id == request_id, Request.customer_id == current_user.id)
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@router.post("/requests/{request_id}/cancel", response_model=RequestOut)
async def cancel_request(
    request_id: UUID,
    reason: str = "Customer cancelled",
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Request).where(
            and_(Request.id == request_id, Request.customer_id == current_user.id)
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.request_status in (RequestStatus.completed, RequestStatus.cancelled):
        raise HTTPException(status_code=400, detail="Request already in terminal state")

    req.request_status = RequestStatus.cancelled
    req.cancelled_at = datetime.now(timezone.utc)
    req.cancellation_reason = reason
    await db.flush()
    return req


# ─── Billing & Payments ───────────────────────────────────────────────────────

@router.get("/billing/{request_id}", response_model=BillingOut)
async def get_billing(
    request_id: UUID,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Billing).where(
            and_(Billing.request_id == request_id, Billing.customer_id == current_user.id)
        )
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing record not found")
    return billing


@router.post("/payments/initiate", response_model=TransactionOut)
async def initiate_payment(
    payload: InitiatePaymentRequest,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Billing).where(
            and_(Billing.id == payload.billing_id, Billing.customer_id == current_user.id)
        )
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing not found")

    stk_resp = await mpesa_service.stk_push(
        phone=payload.phone,
        amount=float(billing.total_amount),
        account_reference=str(billing.id)[:10],
        description=f"RideDelivery payment",
    )

    txn = Transaction(
        billing_id=billing.id,
        user_id=current_user.id,
        amount=billing.total_amount,
        payment_method=PaymentMethod.mpesa,
        mpesa_checkout_request_id=stk_resp.get("CheckoutRequestID"),
        mpesa_merchant_request_id=stk_resp.get("MerchantRequestID"),
        mpesa_phone=payload.phone,
        description="M-Pesa STK Push",
    )
    db.add(txn)
    await db.flush()
    return txn


# ─── Ratings ──────────────────────────────────────────────────────────────────

@router.post("/ratings", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
async def submit_rating(
    payload: CreateRatingRequest,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    # Verify the request belongs to this customer
    result = await db.execute(
        select(Request).where(
            and_(
                Request.id == payload.request_id,
                Request.customer_id == current_user.id,
                Request.request_status == RequestStatus.completed,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Completed request not found")

    # Prevent duplicate
    dup = await db.execute(
        select(Rating).where(
            and_(Rating.request_id == payload.request_id, Rating.rater_id == current_user.id)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already rated this trip")

    rating = Rating(
        request_id=payload.request_id,
        rater_id=current_user.id,
        ratee_id=payload.ratee_id,
        score=payload.score,
        comment=payload.comment,
    )
    db.add(rating)
    await db.flush()

    # Update ratee's average rating
    await _update_rating_avg(db, payload.ratee_id)
    return rating


async def _update_rating_avg(db: AsyncSession, user_id: UUID):
    from sqlalchemy import func
    result = await db.execute(
        select(
            func.avg(Rating.score).label("avg"),
            func.count(Rating.id).label("count"),
        ).where(Rating.ratee_id == user_id)
    )
    row = result.one()
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.rating_avg = float(row.avg or 0)
        profile.rating_count = row.count
    await db.flush()


# ─── Favourites ───────────────────────────────────────────────────────────────

@router.post("/favourites/{rider_id}", status_code=status.HTTP_201_CREATED)
async def add_favourite(
    rider_id: UUID,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(FavoriteRider).where(
            and_(FavoriteRider.customer_id == current_user.id, FavoriteRider.rider_id == rider_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already a favourite")

    fav = FavoriteRider(customer_id=current_user.id, rider_id=rider_id)
    db.add(fav)
    await db.flush()
    return {"message": "Rider added to favourites"}


@router.delete("/favourites/{rider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favourite(
    rider_id: UUID,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FavoriteRider).where(
            and_(FavoriteRider.customer_id == current_user.id, FavoriteRider.rider_id == rider_id)
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favourite not found")
    await db.delete(fav)


# ─── Notifications ────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=List[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(_require_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            and_(Notification.id == notification_id, Notification.user_id == current_user.id)
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    await db.flush()
    return {"message": "Marked as read"}
