import logging
from datetime import datetime, timezone

from app.models.appointment import Appointment

logger = logging.getLogger(__name__)


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _build_payload(*, event: str, appointment: Appointment) -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    return {
        "event": event,
        "appointment_id": appointment.id,
        "provider_id": appointment.provider_id,
        "customer_id": appointment.customer_id,
        "scheduled_start": _as_utc_iso(appointment.start_datetime),
        "scheduled_end": _as_utc_iso(appointment.end_datetime),
        "timestamp": now.isoformat(),
    }


def _log_placeholder(payload: dict[str, int | str]) -> None:
    logger.info("notification_placeholder %s", payload)


def send_booking_confirmation(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="appointment_created", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_booking_cancellation(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="appointment_cancelled", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_booking_reschedule(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="appointment_rescheduled", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_booking_reminder(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="appointment_reminder", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_payment_succeeded(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="payment_succeeded", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_payment_failed(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="payment_failed", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_payment_required(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="payment_required", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_booking_auto_canceled_payment_timeout(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="booking_auto_canceled_due_to_payment_timeout", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_refund_initiated(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="refund_initiated", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_refund_succeeded(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="refund_succeeded", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_refund_failed(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="refund_failed", appointment=appointment)
    _log_placeholder(payload)
    return payload


def send_earning_created(appointment: Appointment) -> dict[str, int | str]:
    payload = _build_payload(event="earning_created", appointment=appointment)
    _log_placeholder(payload)
    return payload


def _build_payout_payload(*, event: str, payout) -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    payload: dict[str, int | str] = {
        "event": event,
        "payout_id": payout.id,
        "provider_id": payout.provider_id,
        "total_amount_minor": int(payout.total_amount_minor),
        "currency": payout.currency,
        "timestamp": now.isoformat(),
    }
    if payout.provider_payout_reference:
        payload["provider_payout_reference"] = payout.provider_payout_reference
    return payload


def send_payout_created(payout) -> dict[str, int | str]:
    payload = _build_payout_payload(event="payout_created", payout=payout)
    _log_placeholder(payload)
    return payload


def send_payout_completed(payout) -> dict[str, int | str]:
    payload = _build_payout_payload(event="payout_completed", payout=payout)
    _log_placeholder(payload)
    return payload


def send_payout_failed(payout) -> dict[str, int | str]:
    payload = _build_payout_payload(event="payout_failed", payout=payout)
    _log_placeholder(payload)
    return payload
