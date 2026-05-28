from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from src.database import Base
from src.models.mixin import StatusFlagMixin, TimestampMixin
from src.models.enums import UserRole


class User(Base, TimestampMixin, StatusFlagMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    roles = relationship("UserRoleMap", back_populates="user", cascade="all, delete-orphan")
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    location = relationship("UserLocation", back_populates="user", uselist=False, cascade="all, delete-orphan")
    requests_made = relationship("Request", foreign_keys="Request.customer_id", back_populates="customer")
    assignments = relationship("RequestAssignment", foreign_keys="RequestAssignment.rider_id", back_populates="rider")
    billings = relationship("Billing", foreign_keys="Billing.customer_id", back_populates="customer")
    transactions = relationship("Transaction", foreign_keys="Transaction.user_id", back_populates="user")
    given_ratings = relationship("Rating", foreign_keys="Rating.rater_id", back_populates="rater")
    received_ratings = relationship("Rating", foreign_keys="Rating.ratee_id", back_populates="ratee")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    favorite_riders = relationship("FavoriteRider", foreign_keys="FavoriteRider.customer_id", back_populates="customer")
    favourited_by = relationship("FavoriteRider", foreign_keys="FavoriteRider.rider_id", back_populates="rider")

    def __repr__(self):
        return f"<User {self.email}>"


class UserRoleMap(Base, TimestampMixin, StatusFlagMixin):
    """Many-to-many: a user may hold multiple roles."""
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)

    user = relationship("User", back_populates="roles")

    __table_args__ = (Index("ix_user_roles_user_role", "user_id", "role", unique=True),)


class UserProfile(Base, TimestampMixin, StatusFlagMixin):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    vehicle_type = Column(String(50), nullable=True)
    vehicle_plate = Column(String(20), nullable=True)
    national_id = Column(String(50), nullable=True)
    is_available = Column(Boolean, default=False, nullable=False)
    rating_avg = Column(Float, default=0.0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    total_trips = Column(Integer, default=0, nullable=False)
    wallet_balance = Column(Numeric(12, 2), default=0.00, nullable=False)

    user = relationship("User", back_populates="profile")


class UserLocation(Base, TimestampMixin, StatusFlagMixin):
    """Real-time location updated by the rider app on a heartbeat."""
    __tablename__ = "user_locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    heading = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)

    user = relationship("User", back_populates="location")

    __table_args__ = (Index("ix_user_locations_coords", "latitude", "longitude"),)


class FavoriteRider(Base, TimestampMixin, StatusFlagMixin):
    """Customers can save preferred riders."""
    __tablename__ = "favorite_riders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rider_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    customer = relationship("User", foreign_keys=[customer_id], back_populates="favorite_riders")
    rider = relationship("User", foreign_keys=[rider_id], back_populates="favourited_by")

    __table_args__ = (
        Index("ix_favorite_riders_customer_rider", "customer_id", "rider_id", unique=True),
    )
