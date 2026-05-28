import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.misc import Notification
from src.models.user import User
from src.models.enums import NotificationType

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    notification_type: NotificationType,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
    )
    db.add(notif)
    await db.flush()
    logger.info("Notification created for user %s: %s", user_id, title)
    # TODO: Integrate Firebase FCM / Africa's Talking SMS here
    return notif


async def notify_favourite_rider_online(db: AsyncSession, rider_id: UUID) -> None:
    """
    When a rider marks themselves available, notify all customers
    who have that rider saved as a favourite.
    """
    from src.models.user import FavoriteRider

    result = await db.execute(
        select(FavoriteRider).where(FavoriteRider.rider_id == rider_id)
    )
    favorites = result.scalars().all()

    rider_result = await db.execute(select(User).where(User.id == rider_id))
    rider = rider_result.scalar_one_or_none()
    if not rider or not rider.profile:
        return

    rider_name = f"{rider.profile.first_name} {rider.profile.last_name}" if rider.profile else "Your rider"

    for fav in favorites:
        await create_notification(
            db,
            user_id=fav.customer_id,
            notification_type=NotificationType.favourite_rider_online,
            title="Favourite Rider Online!",
            body=f"{rider_name} is now available and ready for your request.",
            data={"rider_id": str(rider_id)},
        )
