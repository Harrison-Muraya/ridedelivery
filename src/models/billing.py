from sqlalchemy import (
    Column, String, Float, Boolean, DateTime,
    ForeignKey, Enum as SAEnum, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from src.database import Base
from .mixin import TimestampMixin, StatusFlagMixin
from .enums import BillingStatus, PaymentMethod, TransactionStatus


class Billing(Base, TimestampMixin, StatusFlagMixin):
    """One billing record per completed request."""
    __tablename__ = "billing"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.id"), unique=True, nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    rider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    base_fare = Column(Numeric(10, 2), nullable=False)
    distance_charge = Column(Numeric(10, 2), nullable=False)
    time_charge = Column(Numeric(10, 2), nullable=False, default=0.00)
    surge_charge = Column(Numeric(10, 2), nullable=False, default=0.00)
    discount = Column(Numeric(10, 2), nullable=False, default=0.00)
    total_amount = Column(Numeric(10, 2), nullable=False)

    billing_status = Column(SAEnum(BillingStatus), nullable=False, default=BillingStatus.unpaid)
    payment_method = Column(SAEnum(PaymentMethod), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    platform_commission_pct = Column(Float, default=20.0, nullable=False)
    rider_earnings = Column(Numeric(10, 2), nullable=True)

    request = relationship("Request", back_populates="billing")
    customer = relationship("User", foreign_keys=[customer_id], back_populates="billings")
    rider_user = relationship("User", foreign_keys=[rider_id])
    transactions = relationship("Transaction", back_populates="billing", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_billing_customer_status", "customer_id", "billing_status"),
    )


class Transaction(Base, TimestampMixin, StatusFlagMixin):
    """Every payment attempt is tracked here."""
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    billing_id = Column(UUID(as_uuid=True), ForeignKey("billing.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(5), default="KES", nullable=False)
    payment_method = Column(SAEnum(PaymentMethod), nullable=False)
    transaction_status = Column(SAEnum(TransactionStatus), nullable=False, default=TransactionStatus.pending)

    mpesa_checkout_request_id = Column(String(255), nullable=True, index=True)
    mpesa_merchant_request_id = Column(String(255), nullable=True)
    mpesa_receipt_number = Column(String(100), nullable=True, unique=True)
    mpesa_phone = Column(String(20), nullable=True)

    reference = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    billing = relationship("Billing", back_populates="transactions")
    user = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_billing_status", "billing_id", "transaction_status"),
    )
