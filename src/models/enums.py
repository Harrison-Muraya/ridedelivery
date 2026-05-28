import enum


class UserRole(str, enum.Enum):
    customer = "customer"
    rider = "rider"
    admin = "admin"


class RequestType(str, enum.Enum):
    ride = "ride"
    delivery = "delivery"


class RequestStatus(str, enum.Enum):
    pending = "pending"
    searching = "searching"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    admin_escalated = "admin_escalated"


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    timeout = "timeout"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class PaymentMethod(str, enum.Enum):
    mpesa = "mpesa"
    cash = "cash"
    wallet = "wallet"


class BillingStatus(str, enum.Enum):
    unpaid = "unpaid"
    paid = "paid"
    partially_paid = "partially_paid"
    waived = "waived"


class NotificationType(str, enum.Enum):
    new_request = "new_request"
    request_accepted = "request_accepted"
    rider_arrived = "rider_arrived"
    trip_started = "trip_started"
    trip_completed = "trip_completed"
    payment_received = "payment_received"
    favourite_rider_online = "favourite_rider_online"
    admin_alert = "admin_alert"
    request_escalated = "request_escalated"
