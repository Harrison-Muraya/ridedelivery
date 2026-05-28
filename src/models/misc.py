from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from src.database import Base
from .mixin import TimestampMixin, StatusFlagMixin
from .enums import RequestType, NotificationType


class PricingConfig(Base, TimestampMixin, StatusFlagMixin):
    """Admin-managed pricing rules."""
    __tablename__ = "pricing_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_type = Column(SAEnum(RequestType), nullable=False)
    vehicle_type = Column(String(50), nullable=False, default="motorbike")
    base_fare = Column(Numeric(10, 2), nullable=False, default=50.00)
    per_km_rate = Column(Numeric(10, 2), nullable=False, default=50.00)
    per_minute_rate = Column(Numeric(10, 2), nullable=False, default=2.00)
    minimum_fare = Column(Numeric(10, 2), nullable=False, default=100.00)
    surge_multiplier = Column(Float, default=1.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_pricing_config_type_vehicle", "request_type", "vehicle_type"),
    )


class Rating(Base, TimestampMixin, StatusFlagMixin):
    """Bidirectional: customer rates rider AND rider rates customer."""
    __tablename__ = "ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.id"), nullable=False, index=True)
    rater_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ratee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    score = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)

    rater = relationship("User", foreign_keys=[rater_id], back_populates="given_ratings")
    ratee = relationship("User", foreign_keys=[ratee_id], back_populates="received_ratings")

    __table_args__ = (
        Index("ix_ratings_request_rater", "request_id", "rater_id", unique=True),
        Index("ix_ratings_ratee", "ratee_id"),
    )


class Notification(Base, TimestampMixin, StatusFlagMixin):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
    )


class SystemLog(Base, TimestampMixin, StatusFlagMixin):
    """Audit trail for important system events."""
    __tablename__ = "system_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)
    entity = Column(String(100), nullable=True)
    entity_id = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
