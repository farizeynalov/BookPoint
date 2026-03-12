from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from threading import Lock
import time

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.observability.metrics import increment_counter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    limit: int
    remaining: int
    policy_name: str
    key_fingerprint: str
    backend: str


@dataclass
class _MemoryEntry:
    count: int
    expires_at: float


class _MemoryRateStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, _MemoryEntry] = {}

    def hit(self, *, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.time()
        with self._lock:
            self._cleanup(now)
            entry = self._entries.get(key)
            if entry is None or entry.expires_at <= now:
                expires_at = now + window_seconds
                entry = _MemoryEntry(count=1, expires_at=expires_at)
                self._entries[key] = entry
            else:
                entry.count += 1

            allowed = entry.count <= limit
            retry_after = max(int(entry.expires_at - now), 1) if not allowed else max(int(entry.expires_at - now), 0)
            remaining = max(limit - entry.count, 0)
            return allowed, retry_after, remaining

    def reset(self) -> None:
        with self._lock:
            self._entries = {}

    def _cleanup(self, now: float) -> None:
        stale_keys = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in stale_keys:
            self._entries.pop(key, None)


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryRateStore()
        self._redis_client: Redis | None = None
        self._redis_lock = Lock()
        self._redis_disabled_until = 0.0

    def check(self, *, policy: RateLimitPolicy, key: str) -> RateLimitDecision:
        key_fingerprint = hashlib.sha256(f"{policy.name}:{key}".encode("utf-8")).hexdigest()
        if not settings.enable_rate_limiting:
            increment_counter("rate_limit_allowed_total")
            return RateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                limit=policy.limit,
                remaining=policy.limit,
                policy_name=policy.name,
                key_fingerprint=key_fingerprint,
                backend="disabled",
            )

        storage_key = f"rl:{policy.name}:{key_fingerprint}"
        backend = "memory"
        allowed = True
        retry_after = 0
        remaining = policy.limit

        if settings.rate_limit_use_redis:
            redis_client = self._get_redis_client()
            if redis_client is not None:
                try:
                    allowed, retry_after, remaining = self._hit_redis(
                        redis_client,
                        key=storage_key,
                        limit=policy.limit,
                        window_seconds=policy.window_seconds,
                    )
                    backend = "redis"
                except RedisError:
                    self._disable_redis_temporarily()
                    logger.exception("rate_limiter_redis_failed policy=%s", policy.name)
                    if not settings.rate_limit_fallback_to_memory:
                        # Fail open for availability when Redis is unavailable and fallback is disabled.
                        increment_counter("rate_limit_allowed_total")
                        return RateLimitDecision(
                            allowed=True,
                            retry_after_seconds=0,
                            limit=policy.limit,
                            remaining=policy.limit,
                            policy_name=policy.name,
                            key_fingerprint=key_fingerprint,
                            backend="redis_unavailable",
                        )

        if backend != "redis":
            allowed, retry_after, remaining = self._memory.hit(
                key=storage_key,
                limit=policy.limit,
                window_seconds=policy.window_seconds,
            )

        if allowed:
            increment_counter("rate_limit_allowed_total")
        else:
            increment_counter("rate_limit_hits_total")

        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=retry_after,
            limit=policy.limit,
            remaining=remaining,
            policy_name=policy.name,
            key_fingerprint=key_fingerprint,
            backend=backend,
        )

    def reset_for_tests(self) -> None:
        self._memory.reset()
        with self._redis_lock:
            self._redis_client = None
            self._redis_disabled_until = 0.0

    def _get_redis_client(self) -> Redis | None:
        if time.time() < self._redis_disabled_until:
            return None
        with self._redis_lock:
            if self._redis_client is None:
                self._redis_client = Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.25,
                    socket_timeout=0.25,
                )
            return self._redis_client

    def _disable_redis_temporarily(self) -> None:
        with self._redis_lock:
            self._redis_disabled_until = time.time() + 5

    @staticmethod
    def _hit_redis(redis_client: Redis, *, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        count = int(redis_client.incr(key))
        if count == 1:
            redis_client.expire(key, window_seconds)
        ttl = int(redis_client.ttl(key))
        if ttl < 0:
            redis_client.expire(key, window_seconds)
            ttl = window_seconds
        allowed = count <= limit
        retry_after = max(ttl, 1) if not allowed else max(ttl, 0)
        remaining = max(limit - count, 0)
        return allowed, retry_after, remaining


rate_limiter = RateLimiter()


def get_rate_limit_policy(policy_name: str) -> RateLimitPolicy:
    policy_map: dict[str, tuple[int, int]] = {
        "public_slots": (
            settings.rate_limit_public_slots_limit,
            settings.rate_limit_public_slots_window_seconds,
        ),
        "public_booking": (
            settings.rate_limit_public_booking_limit,
            settings.rate_limit_public_booking_window_seconds,
        ),
        "public_booking_duplicate": (
            settings.rate_limit_public_booking_duplicate_limit,
            settings.rate_limit_public_booking_duplicate_window_seconds,
        ),
        "customer_booking_get": (
            settings.rate_limit_customer_booking_get_limit,
            settings.rate_limit_customer_booking_get_window_seconds,
        ),
        "customer_booking_action": (
            settings.rate_limit_customer_booking_action_limit,
            settings.rate_limit_customer_booking_action_window_seconds,
        ),
        "customer_invalid_token": (
            settings.rate_limit_customer_invalid_token_limit,
            settings.rate_limit_customer_invalid_token_window_seconds,
        ),
        "payment_confirm": (
            settings.rate_limit_payment_confirm_limit,
            settings.rate_limit_payment_confirm_window_seconds,
        ),
        "payout_create": (
            settings.rate_limit_payout_create_limit,
            settings.rate_limit_payout_create_window_seconds,
        ),
        "manual_refund": (
            settings.rate_limit_manual_refund_limit,
            settings.rate_limit_manual_refund_window_seconds,
        ),
        "admin_events": (
            settings.rate_limit_admin_events_limit,
            settings.rate_limit_admin_events_window_seconds,
        ),
    }
    if policy_name not in policy_map:
        raise KeyError(f"Unknown rate limit policy: {policy_name}")
    limit, window_seconds = policy_map[policy_name]
    return RateLimitPolicy(name=policy_name, limit=limit, window_seconds=window_seconds)
