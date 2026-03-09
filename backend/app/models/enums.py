from enum import Enum


class MembershipRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"
    ASSISTANT = "assistant"


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
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


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
