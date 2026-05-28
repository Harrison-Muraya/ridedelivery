from sqlalchemy import (
    Column, String, Integer, Float, DateTime,
    ForeignKey, Text, Enum as SAEnum, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from src.database import Base
from .mixin import TimestampMixin, StatusFlagMixin
from .enums import RequestType, RequestStatus, AssignmentStatus


class Request(Base, TimestampMixin, StatusFlagMixin):
    """A ride or delivery job requested by a customer."""
    __tablename__ = "requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    preferred_rider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    request_type = Column(SAEnum(RequestType), nullable=False)
    request_status = Column(SAEnum(RequestStatus), nullable=False, default=RequestStatus.pending)

    pickup_latitude = Column(Float, nullable=False)
    pickup_longitude = Column(Float, nullable=False)
    pickup_address = Column(String(500), nullable=False)

    dropoff_latitude = Column(Float, nullable=False)
    dropoff_longitude = Column(Float, nullable=False)
    dropoff_address = Column(String(500), nullable=False)

    # Delivery-specific
    package_description = Column(Text, nullable=True)
    recipient_name = Column(String(200), nullable=True)
    recipient_phone = Column(String(20), nullable=True)

    distance_km = Column(Float, nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    estimated_fare = Column(Numeric(10, 2), nullable=True)
    final_fare = Column(Numeric(10, 2), nullable=True)

    accepted_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)

    customer = relationship("User", foreign_keys=[customer_id], back_populates="requests_made")
    preferred_rider = relationship("User", foreign_keys=[preferred_rider_id])
    assignments = relationship("RequestAssignment", back_populates="request",
                               cascade="all, delete-orphan", order_by="RequestAssignment.created_at")
    billing = relationship("Billing", back_populates="request", uselist=False)

    __table_args__ = (
        Index("ix_requests_customer_status", "customer_id", "request_status"),
    )


class RequestAssignment(Base, TimestampMixin, StatusFlagMixin):
    """Each row is one attempt to assign a rider to a request."""
    __tablename__ = "request_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    rider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    assignment_status = Column(SAEnum(AssignmentStatus), nullable=False, default=AssignmentStatus.pending)
    attempt_number = Column(Integer, nullable=False, default=1)
    distance_at_assignment_km = Column(Float, nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    timeout_task_id = Column(String(255), nullable=True)

    request = relationship("Request", back_populates="assignments")
    rider = relationship("User", foreign_keys=[rider_id], back_populates="assignments")

    __table_args__ = (
        Index("ix_assignments_request_rider", "request_id", "rider_id"),
    )
