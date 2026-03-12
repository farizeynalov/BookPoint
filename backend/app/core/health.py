from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from redis import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal


@dataclass(frozen=True)
class DependencyHealth:
    name: str
    ok: bool
    latency_ms: float
    error: str | None = None

    def as_payload(self) -> dict[str, str | float]:
        payload: dict[str, str | float] = {
            "status": "ok" if self.ok else "error",
            "latency_ms": round(self.latency_ms, 2),
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


def check_database_health() -> DependencyHealth:
    started = perf_counter()
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        return DependencyHealth(name="database", ok=True, latency_ms=(perf_counter() - started) * 1000)
    except Exception as exc:
        return DependencyHealth(
            name="database",
            ok=False,
            latency_ms=(perf_counter() - started) * 1000,
            error=exc.__class__.__name__,
        )
    finally:
        session.close()


def check_redis_health() -> DependencyHealth:
    started = perf_counter()
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=False,
    )
    try:
        client.ping()
        return DependencyHealth(name="redis", ok=True, latency_ms=(perf_counter() - started) * 1000)
    except Exception as exc:
        return DependencyHealth(
            name="redis",
            ok=False,
            latency_ms=(perf_counter() - started) * 1000,
            error=exc.__class__.__name__,
        )
    finally:
        client.close()


def build_readiness_payload() -> tuple[bool, dict[str, object]]:
    checks = [check_database_health(), check_redis_health()]
    ready = all(check.ok for check in checks)
    payload = {
        "status": "ok" if ready else "degraded",
        "checks": {check.name: check.as_payload() for check in checks},
    }
    return ready, payload
