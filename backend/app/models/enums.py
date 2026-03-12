from enum import Enum


class MembershipRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    PROVIDER = "provider"
    STAFF = "staff"


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    WEB = "web"
    MOBILE = "mobile"


class BookingChannel(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    WEB = "web"
    MOBILE = "mobile"
    DASHBOARD = "dashboard"
    ADMIN = "admin"


class AppointmentStatus(str, Enum):
    PENDING = "pending"
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class PaymentType(str, Enum):
    FULL = "full"
    DEPOSIT = "deposit"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class NotificationType(str, Enum):
    REMINDER = "reminder"
    STATUS_UPDATE = "status_update"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
