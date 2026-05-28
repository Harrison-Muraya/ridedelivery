from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.models.enums import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    notification_type: NotificationType
    title: str
    body: str
    is_read: bool
    created_at: datetime
