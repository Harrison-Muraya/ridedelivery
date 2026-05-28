"""
Celery tasks for sending notifications.
Keeps the API response fast — notifications are fire-and-forget.
"""

import logging
from uuid import UUID

from src.jobs.celery_app import celery_app
from src.config import settings

logger = logging.getLogger(__name__)


def _get_sync_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(bind=engine)
    return Session()


@celery_app.task(name="src.jobs.notification_tasks.send_rider_assignment_notification")
def send_rider_assignment_notification(rider_id: str, request_id: str, assignment_id: str):
    """Notify rider of a new job assignment."""
    from src.models.misc import Notification
    from src.models.enums import NotificationType

    db = _get_sync_db()
    try:
        notif = Notification(
            user_id=UUID(rider_id),
            notification_type=NotificationType.new_request,
            title="New Job Available!",
            body="A customer needs a ride. Tap to accept or reject.",
            data=str({"request_id": request_id, "assignment_id": assignment_id}),
        )
        db.add(notif)
        db.commit()
        logger.info("Notified rider %s of assignment %s", rider_id, assignment_id)
        # TODO: Push FCM notification here
    except Exception:
        db.rollback()
        logger.exception("send_rider_assignment_notification failed")
    finally:
        db.close()


@celery_app.task(name="src.jobs.notification_tasks.notify_customer_accepted")
def notify_customer_accepted(customer_id: str, request_id: str, rider_name: str):
    from src.models.misc import Notification
    from src.models.enums import NotificationType

    db = _get_sync_db()
    try:
        notif = Notification(
            user_id=UUID(customer_id),
            notification_type=NotificationType.request_accepted,
            title="Rider Accepted Your Request",
            body=f"{rider_name} is on the way!",
            data=str({"request_id": request_id}),
        )
        db.add(notif)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("notify_customer_accepted failed")
    finally:
        db.close()


@celery_app.task(name="src.jobs.notification_tasks.notify_trip_completed")
def notify_trip_completed(customer_id: str, rider_id: str, request_id: str, total_amount: str):
    from src.models.misc import Notification
    from src.models.enums import NotificationType

    db = _get_sync_db()
    try:
        for user_id, body in [
            (customer_id, f"Trip completed! Total: KSH {total_amount}. Please rate your rider."),
            (rider_id, f"Trip completed! You earned KSH {total_amount}. Please rate your customer."),
        ]:
            notif = Notification(
                user_id=UUID(user_id),
                notification_type=NotificationType.trip_completed,
                title="Trip Completed",
                body=body,
                data=str({"request_id": request_id}),
            )
            db.add(notif)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("notify_trip_completed failed")
    finally:
        db.close()


@celery_app.task(name="src.jobs.notification_tasks.notify_favourite_rider_online_task")
def notify_favourite_rider_online_task(rider_id: str):
    """
    Async job: notify customers who favourited this rider that they are online.
    Triggered when a rider toggles is_available = True.
    """
    from src.models.user import FavoriteRider, User
    from src.models.misc import Notification
    from src.models.enums import NotificationType

    db = _get_sync_db()
    try:
        favorites = db.query(FavoriteRider).filter(
            FavoriteRider.rider_id == UUID(rider_id)
        ).all()

        rider = db.query(User).filter(User.id == UUID(rider_id)).first()
        if not rider or not rider.profile:
            return

        name = f"{rider.profile.first_name} {rider.profile.last_name}"
        for fav in favorites:
            notif = Notification(
                user_id=fav.customer_id,
                notification_type=NotificationType.favourite_rider_online,
                title="Favourite Rider Online!",
                body=f"{name} is now available for your next ride or delivery.",
                data=str({"rider_id": rider_id}),
            )
            db.add(notif)
        db.commit()
        logger.info("Notified %d customers that rider %s is online", len(favorites), rider_id)
    except Exception:
        db.rollback()
        logger.exception("notify_favourite_rider_online_task failed")
    finally:
        db.close()
