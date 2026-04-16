# BookPoint

A production-grade, multi-tenant appointment booking backend built with Python 3.12 and FastAPI. BookPoint powers service businesses — salons, clinics, consultants — with a full scheduling engine, payment processing, commissions, payouts, and a conversational **WhatsApp Cloud API** booking channel.

---

## Features

### Multi-Tenant Organization System
- Organizations with multiple locations, providers, and services
- Role-based membership: `OWNER`, `ADMIN`, `PROVIDER`, `STAFF`
- Platform admin fast-path with cross-tenant access
- Per-org timezone support via `ZoneInfo`

### Scheduling Engine
- Buffer-aware slot generation (`buffer_before_minutes` / `buffer_after_minutes` per service)
- Weekly availability rules, date overrides, and time-off blocks per provider
- Timezone-correct slot listing up to 31 days ahead
- Conflict detection across all active appointments

### Appointment Lifecycle
- Public discovery and booking via unauthenticated endpoints
- Full status machine: `PENDING` → `CONFIRMED` → `COMPLETED` / `CANCELLED`
- `PENDING_PAYMENT` state with auto-expiry via Celery beat (configurable window)
- Booking reference (`BKP-XXXXXX`) and per-appointment access token for customer self-service

### Payments, Refunds & Payouts
- Deposit and full-prepayment models with per-service `payment_type`
- Three cancellation/refund policies: `FLEXIBLE` (100%), `MODERATE` (deposit-aware), `STRICT` (window-based 50%/0%)
- Per-org commission model: `FIXED` or `PERCENTAGE` (stored as `Numeric(5,4)`)
- Provider earnings tracked per payment; payout failure resets earnings to `READY_FOR_PAYOUT`
- Post-payout refund adjustments netted against next payout
- All amounts in minor currency units; `ZERO_DECIMAL_CURRENCIES` handled (JPY, KRW, etc.)
- Mock payment/refund/payout provider included; designed as drop-in slot for Stripe or Adyen

### WhatsApp Conversational Booking
- End-to-end booking flow via WhatsApp Cloud API (Meta Graph API v23.0)
- Stateful conversation engine: organization → location → service → provider → date → slot → confirm
- Customers can view upcoming bookings, cancel, and reschedule entirely over WhatsApp
- HMAC SHA256 webhook validation (`X-Hub-Signature-256`)
- Exponential-backoff retry on 5xx from Meta
- Message deduplication at DB level via unique index on `(channel, direction, external_message_id)`
- Per-user rate limiting with domain event logging on denial

### Production Hardening
- **JWT authentication** — HS256 bearer tokens via `python-jose`, Argon2 password hashing via `pwdlib`
- **Idempotency** — SHA256 request hash stored in DB; replays with `X-Idempotent-Replayed: true`
- **Request ID correlation** — `X-Request-ID` middleware injected into all log records via `ContextVar`
- **Rate limiting** — 11 named policies (memory or Redis backend); configurable per endpoint
- **Prometheus metrics** — 25 counters at `/metrics` (bookings, payments, WhatsApp flows, rate-limit hits, etc.)
- **Domain event audit log** — every state transition recorded; payload sanitization redacts tokens/secrets/passwords
- **Operational cleanup** — Celery beat deletes expired domain events and idempotency keys per retention config
- **Runtime config validation** — `scripts/check_runtime.py` refuses unsafe production defaults

### Background Workers (Celery + Redis)
- Payment expiry checker (default every 60s)
- Appointment reminder dispatcher (default 60-min lookahead)
- Payout processor (default every 300s)
- Operational cleanup (default every 3600s)

---

## Tech Stack

| Layer | Package |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI 0.115+ |
| ASGI server | Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Cache / broker | Redis 7 |
| Task queue | Celery 5.4+ |
| JWT | python-jose[cryptography] |
| Password hashing | pwdlib[argon2] |
| Config | pydantic-settings |
| Messaging | WhatsApp Business Cloud API |
| Testing | pytest, pytest-asyncio |

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                     # App factory, middlewares, exception handlers
│   ├── api/
│   │   └── routers/                # 18 router modules (auth, orgs, providers, services,
│   │                               #   appointments, payments, payouts, discovery,
│   │                               #   scheduling, customers, whatsapp, admin, ...)
│   ├── core/                       # Config, security, logging, request-ID, health checks
│   ├── db/                         # SQLAlchemy engine, session, Alembic base
│   ├── dependencies/               # Auth guards, rate-limit enforcement
│   ├── middleware/                  # Request-ID ingress + sanitization
│   ├── models/                     # 25 SQLAlchemy models
│   ├── repositories/               # 24 data-access classes
│   ├── schemas/                    # 20 Pydantic v2 DTOs
│   ├── services/
│   │   ├── appointment_service.py
│   │   ├── scheduling_service.py
│   │   ├── discovery_service.py
│   │   ├── payments/               # payment, earning, refund, payout, mock provider
│   │   ├── whatsapp/               # gateway, parser, state-machine service
│   │   ├── notifications/          # Celery dispatcher + placeholder service
│   │   ├── observability/          # Domain events + Prometheus counters
│   │   └── operations/             # Cleanup + migration status
│   └── utils/                      # Currency, datetime, phone, slug helpers
├── alembic/
│   └── versions/                   # 14 migrations
├── scripts/                        # seed.py, check_runtime.py, DB backup/restore (.sh + .ps1)
├── tests/                          # 30 test files, 221 tests
├── Dockerfile
├── docker-compose.yml              # api + worker + beat + postgres:16 + redis:7
└── pyproject.toml
```

---

## Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL 16
- Redis 7
- WhatsApp Business Cloud API credentials (optional — disable with `WHATSAPP_ENABLED=false`)

### Installation

```bash
git clone https://github.com/farizeynalov/BookPoint.git
cd BookPoint/backend

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and fill in the required values:

```env
# Core
APP_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/bookpoint
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# WhatsApp (set WHATSAPP_ENABLED=false to skip)
WHATSAPP_ENABLED=true
WHATSAPP_VERIFY_TOKEN=your-verify-token
WHATSAPP_ACCESS_TOKEN=your-access-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
WHATSAPP_APP_SECRET=your-app-secret

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

See `app/core/config.py` for the full list of 50+ options including rate-limit policies, payment settings, retention periods, and feature flags.

### Run Migrations

```bash
alembic upgrade head
```

### Start the API

```bash
uvicorn app.main:app --reload
```

Swagger docs at `http://localhost:8000/docs` (requires `ENABLE_DOCS=true`).

### Start Workers

```bash
# Background task worker
celery -A app.workers.celery_app:celery_app worker

# Scheduled tasks (payment expiry, reminders, payouts, cleanup)
celery -A app.workers.celery_app:celery_app beat
```

### Docker (all services)

```bash
docker-compose up --build
```

Starts: API, Celery worker, Celery beat, PostgreSQL 16, Redis 7.

---

## Running Tests

```bash
pytest
```

221 tests across 30 files. Uses SQLite in-memory — no external services required.

---

## API Overview

All routes under `/api/v1`.

| Group | Notable Endpoints |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me` |
| Discovery (public) | Org/location/service/provider listing, slot availability, `POST /discovery/bookings` |
| Customer self-service | Token-gated booking view, cancel, reschedule (`X-Booking-Token` header) |
| Organizations | CRUD + member management |
| Locations | CRUD + provider/service assignment per location |
| Providers | CRUD + activate/deactivate + earnings + availability/overrides/time-off |
| Services | CRUD + provider assignments |
| Appointments | CRUD + cancel + reschedule |
| Payments | Webhook confirm + manual refund |
| Payouts | Create payout per provider |
| WhatsApp | Webhook verification (`GET`) + inbound message handler (`POST`) |
| Admin | Ping, stats, readiness, domain event log |
| Health | `/health/live`, `/health/ready`, `/health` |
| Metrics | `/metrics` — Prometheus text format |

---

## WhatsApp Booking Flow

Customers book entirely over WhatsApp with no app or login required:

```
"hi" / "hello"
  → Select organization
  → Select location         (skipped if only one)
  → Select service
  → Select provider
  → Select date             (next 7 days)
  → Select time slot
  → Confirm booking
  → Receive booking reference (e.g. BKP-A1B2C3)

Type "menu" at any point to return to the main menu.
Select "My Bookings" to view, cancel, or reschedule upcoming appointments.
```

---

## Seed Data

```bash
python scripts/seed.py
```

Creates demo organizations, providers, services, and users for local development.

---

## Author

**Fariz Zeynalov**
[LinkedIn](https://www.linkedin.com/in/farizeynalov/) · [GitHub](https://github.com/farizeynalov)
