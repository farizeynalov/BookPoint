from __future__ import annotations

from threading import Lock

DEFAULT_COUNTERS = (
    "bookings_created_total",
    "bookings_canceled_total",
    "bookings_rescheduled_total",
    "payments_required_total",
    "payments_succeeded_total",
    "payments_failed_total",
    "refunds_succeeded_total",
    "refunds_failed_total",
    "payouts_created_total",
    "payouts_completed_total",
    "payouts_failed_total",
    "reminders_sent_total",
    "idempotency_replays_total",
    "reminders_scheduled_total",
    "worker_runs_total",
    "worker_failures_total",
    "rate_limit_hits_total",
    "rate_limit_allowed_total",
    "whatsapp_webhook_received_total",
    "whatsapp_outbound_sent_total",
    "whatsapp_outbound_failed_total",
    "whatsapp_conversation_started_total",
    "whatsapp_bookings_completed_total",
    "whatsapp_cancellations_completed_total",
    "whatsapp_reschedules_completed_total",
)


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters = {name: 0 for name in DEFAULT_COUNTERS}
        self._lock = Lock()

    def increment(self, name: str, value: int = 1) -> None:
        if value == 0:
            return
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + int(value)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        for name in sorted(snapshot.keys()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {snapshot[name]}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters = {name: 0 for name in DEFAULT_COUNTERS}


metrics_registry = MetricsRegistry()


def increment_counter(name: str, value: int = 1) -> None:
    metrics_registry.increment(name, value)


def render_prometheus_metrics() -> str:
    return metrics_registry.render_prometheus()


def reset_metrics_for_tests() -> None:
    metrics_registry.reset()
