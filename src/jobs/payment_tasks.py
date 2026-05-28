"""
Celery tasks for payment processing.
M-Pesa callbacks come asynchronously — we process them here off the main thread.
"""

import logging
from decimal import Decimal
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


@celery_app.task(name="src.jobs.payment_tasks.process_mpesa_callback")
def process_mpesa_callback(checkout_request_id: str, result_code: int, receipt_number: str = None):
    """
    Process the result of an M-Pesa STK push callback.
    result_code == 0 means success.
    """
    from src.models.billing import Transaction, Billing
    from src.models.enums import TransactionStatus, BillingStatus
    from datetime import datetime, timezone

    db = _get_sync_db()
    try:
        txn = db.query(Transaction).filter(
            Transaction.mpesa_checkout_request_id == checkout_request_id
        ).first()

        if not txn:
            logger.error("Transaction not found for checkout_request_id %s", checkout_request_id)
            return

        if result_code == 0:
            txn.transaction_status = TransactionStatus.completed
            txn.mpesa_receipt_number = receipt_number
            txn.completed_at = datetime.now(timezone.utc)

            billing = db.query(Billing).filter(Billing.id == txn.billing_id).first()
            if billing:
                billing.billing_status = BillingStatus.paid
                billing.paid_at = datetime.now(timezone.utc)
                billing.payment_method = txn.payment_method

                # Credit rider earnings to wallet
                if billing.rider_id and billing.rider_earnings:
                    from src.models.user import UserProfile
                    rider_profile = db.query(UserProfile).filter(
                        UserProfile.user_id == billing.rider_id
                    ).first()
                    if rider_profile:
                        rider_profile.wallet_balance += billing.rider_earnings

        else:
            txn.transaction_status = TransactionStatus.failed
            txn.failure_reason = f"M-Pesa result code: {result_code}"

        db.commit()
        logger.info(
            "Processed M-Pesa callback for %s: result_code=%d",
            checkout_request_id, result_code,
        )

    except Exception:
        db.rollback()
        logger.exception("process_mpesa_callback failed for %s", checkout_request_id)
    finally:
        db.close()


@celery_app.task(name="src.jobs.payment_tasks.create_billing_record")
def create_billing_record(request_id: str, rider_id: str):
    """
    Create a Billing record once a trip is marked completed.
    Called asynchronously after the rider marks the trip done.
    """
    from src.models.requests import Request
    from src.models.billing import Billing
    from src.models.enums import BillingStatus
    from decimal import Decimal

    db = _get_sync_db()
    try:
        request = db.query(Request).filter(Request.id == UUID(request_id)).first()
        if not request:
            return

        # Check if billing already exists
        existing = db.query(Billing).filter(Billing.request_id == request.id).first()
        if existing:
            return

        total = Decimal(str(request.final_fare or request.estimated_fare or 0))
        commission_pct = Decimal("20.0")
        rider_earnings = total * (1 - commission_pct / 100)

        billing = Billing(
            request_id=request.id,
            customer_id=request.customer_id,
            rider_id=UUID(rider_id),
            base_fare=Decimal("50.00"),
            distance_charge=total - Decimal("50.00"),
            time_charge=Decimal("0.00"),
            surge_charge=Decimal("0.00"),
            discount=Decimal("0.00"),
            total_amount=total,
            platform_commission_pct=float(commission_pct),
            rider_earnings=rider_earnings,
        )
        db.add(billing)
        db.commit()
        logger.info("Created billing record for request %s", request_id)

    except Exception:
        db.rollback()
        logger.exception("create_billing_record failed for request %s", request_id)
    finally:
        db.close()
