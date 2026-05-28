"""
Celery tasks that drive the rider-assignment state machine.

Flow:
  1. dispatch_ride_search     – called when a new Request is created
  2. assignment_timeout_task  – fires after RIDER_RESPONSE_TIMEOUT_SECONDS
     a. marks assignment as timeout
     b. calls dispatch_ride_search again (next attempt)
  3. If MAX_ASSIGNMENT_ATTEMPTS exceeded → escalate_to_admin
"""

import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.jobs.celery_app import celery_app
from src.config import settings

logger = logging.getLogger(__name__)


def _get_sync_db():
    """Create a synchronous DB session for use inside Celery tasks."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(bind=engine)
    return Session()


@celery_app.task(name="src.jobs.ride_tasks.dispatch_ride_search", bind=True, max_retries=3)
def dispatch_ride_search(self, request_id: str):
    """
    Find the nearest available rider and create a RequestAssignment.
    Schedules an assignment_timeout_task to handle non-response.
    """
    from src.models.requests import Request, RequestAssignment
    from src.models.enums import RequestStatus, AssignmentStatus
    from src.models.user import UserProfile, UserLocation, UserRoleMap
    from src.models.enums import UserRole
    from src.services.distance import haversine_km
    from src.jobs.notification_tasks import send_rider_assignment_notification

    db = _get_sync_db()
    try:
        request = (
            db.query(Request)
            .options(selectinload(Request.assignments))
            .filter(Request.id == UUID(request_id))
            .first()
        )
        if not request:
            logger.error("Request %s not found", request_id)
            return

        if request.request_status in (
            RequestStatus.cancelled,
            RequestStatus.completed,
            RequestStatus.assigned,
        ):
            logger.info("Request %s already in terminal/assigned state, skipping", request_id)
            return

        tried_ids = [a.rider_id for a in request.assignments]
        attempt_number = len(tried_ids) + 1

        if attempt_number > settings.MAX_ASSIGNMENT_ATTEMPTS:
            _escalate_to_admin(db, request)
            return

        radius_km = min(
            settings.INITIAL_SEARCH_RADIUS_KM * attempt_number,
            settings.MAX_SEARCH_RADIUS_KM,
        )

        # Find nearest available rider not already tried
        riders = (
            db.query(UserProfile, UserLocation)
            .join(UserLocation, UserLocation.user_id == UserProfile.user_id)
            .join(UserRoleMap, UserRoleMap.user_id == UserProfile.user_id)
            .filter(
                UserProfile.is_available == True,
                UserRoleMap.role == UserRole.rider,
                ~UserProfile.user_id.in_(tried_ids),
            )
            .all()
        )

        candidates = []
        for profile, loc in riders:
            dist = haversine_km(
                request.pickup_latitude, request.pickup_longitude,
                loc.latitude, loc.longitude,
            )
            if dist <= radius_km:
                candidates.append((profile.user_id, dist))

        # Prefer preferred rider if in candidates
        if request.preferred_rider_id:
            preferred = [(uid, d) for uid, d in candidates if uid == request.preferred_rider_id]
            others = [(uid, d) for uid, d in candidates if uid != request.preferred_rider_id]
            candidates = preferred + sorted(others, key=lambda x: x[1])
        else:
            candidates.sort(key=lambda x: x[1])

        if not candidates:
            logger.warning(
                "No riders found for request %s (attempt %d, radius %.1f km)",
                request_id, attempt_number, radius_km,
            )
            if attempt_number >= settings.MAX_ASSIGNMENT_ATTEMPTS:
                _escalate_to_admin(db, request)
            else:
                # Retry after a short delay to wait for riders to come online
                self.apply_async(args=[request_id], countdown=60)
            return

        rider_id, dist_km = candidates[0]

        # Create assignment record
        assignment = RequestAssignment(
            request_id=request.id,
            rider_id=rider_id,
            attempt_number=attempt_number,
            distance_at_assignment_km=dist_km,
        )
        db.add(assignment)
        request.request_status = RequestStatus.searching
        db.commit()
        db.refresh(assignment)

        # Schedule timeout task
        timeout_task = assignment_timeout_task.apply_async(
            args=[str(assignment.id)],
            countdown=settings.RIDER_RESPONSE_TIMEOUT_SECONDS,
        )
        assignment.timeout_task_id = timeout_task.id
        db.commit()

        # Notify the rider
        send_rider_assignment_notification.delay(
            str(rider_id), str(request.id), str(assignment.id)
        )

        logger.info(
            "Assigned request %s to rider %s (attempt %d, dist %.2f km)",
            request_id, rider_id, attempt_number, dist_km,
        )

    except Exception as exc:
        db.rollback()
        logger.exception("dispatch_ride_search failed for request %s", request_id)
        raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()


@celery_app.task(name="src.jobs.ride_tasks.assignment_timeout_task")
def assignment_timeout_task(assignment_id: str):
    """
    Fires when a rider has not responded within the timeout window.
    Marks assignment as timeout and tries the next rider.
    """
    from src.models.requests import RequestAssignment, Request
    from src.models.enums import AssignmentStatus, RequestStatus

    db = _get_sync_db()
    try:
        assignment = db.query(RequestAssignment).filter(
            RequestAssignment.id == UUID(assignment_id)
        ).first()

        if not assignment:
            return
        if assignment.assignment_status != AssignmentStatus.pending:
            # Already responded; timeout irrelevant
            return

        assignment.assignment_status = AssignmentStatus.timeout
        db.commit()

        logger.info("Assignment %s timed out. Searching for next rider.", assignment_id)
        dispatch_ride_search.delay(str(assignment.request_id))

    except Exception:
        db.rollback()
        logger.exception("assignment_timeout_task failed for assignment %s", assignment_id)
    finally:
        db.close()


def _escalate_to_admin(db, request):
    """Mark request as escalated and notify all admins."""
    from src.models.requests import Request
    from src.models.enums import RequestStatus, NotificationType
    from src.models.user import User, UserRoleMap
    from src.models.enums import UserRole
    from src.models.misc import Notification

    request.request_status = RequestStatus.admin_escalated
    db.commit()

    admins = (
        db.query(User)
        .join(UserRoleMap, UserRoleMap.user_id == User.id)
        .filter(UserRoleMap.role == UserRole.admin, User.is_active == True)
        .all()
    )
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            notification_type=NotificationType.request_escalated,
            title="Ride Request Escalated",
            body=f"Request {request.id} could not be assigned after {settings.MAX_ASSIGNMENT_ATTEMPTS} attempts.",
            data=str({"request_id": str(request.id)}),
        )
        db.add(notif)
    db.commit()
    logger.warning("Request %s escalated to admin", request.id)
