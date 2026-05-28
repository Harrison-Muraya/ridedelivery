from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func


class TimestampMixin:
    """Adds created_at and updated_at to every model."""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StatusFlagMixin:
    """Every table has status and flag columns defaulting to '0'."""
    status = Column(String(10), nullable=False, default="0", server_default="0")
    flag = Column(String(10), nullable=False, default="0", server_default="0")
