# BookPoint Backend (Phase 1)

BookPoint is a multi-channel appointment-booking platform for appointment-based professionals and businesses (clinics, salons, barbers, consultants, tutors, etc.).

In this phase, the backend foundation is implemented from zero with a single shared API and single shared database.

## Core Architecture

BookPoint is intentionally **channel-agnostic**:

- WhatsApp bot
- Telegram bot
- Website
- Mobile app
- Provider dashboard
- Admin dashboard

All clients must use the same backend and same database so appointment state stays synchronized.

The backend is the **single source of truth**.

## Phase 1 Scope

Implemented now:

- FastAPI service scaffold with modular structure
- SQLAlchemy 2.x models (normalized schema)
- Alembic migration setup + initial migration
- JWT login foundation for dashboard users
- Organization/member/provider/service/customer domain
- Provider-owned service catalog foundation (`duration`, optional `price`/`currency`, booking buffers)
- Buffer-aware scheduling and overlap validation (`buffer_before`/`buffer_after` applied to blocked intervals)
- Customer channel identity mapping
- Provider availability + time-off foundation
- Provider schedule refinement: split daily windows, date-specific overrides, and time-off-aware slot filtering
- Appointment create/list/cancel/reschedule
- Scheduling slot generation service foundation
- Conversation state / message log / notification data foundations
- Redis + Celery worker placeholders
- Docker + docker-compose local setup
- Pytest scaffold + initial coherent tests
- Seed script with demo data

Intentionally deferred:

- WhatsApp/Telegram integrations
- Web/mobile frontend apps
- Billing/subscription
- Real notification delivery channels
- AI chatbot logic
- Production cloud deployment hardening

## Datetime and Timezone Strategy

- Database columns use timezone-aware datetimes (`TIMESTAMP WITH TIME ZONE` in PostgreSQL).
- Appointment, provider time-off, and notification schedules are stored in UTC.
- `provider_availability` stores recurring weekday + local time windows in the provider organization timezone.
- Slot generation converts local organization windows to UTC and subtracts:
  - provider time-off intervals
  - existing blocking appointments (`pending`, `confirmed`)
- Default operating timezone is `Asia/Baku`.

## Overlap Protection Strategy (Phase 1)

- Appointment create/reschedule now runs with explicit transaction boundaries (`commit`/`rollback` in service layer).
- Provider rows are locked with `SELECT ... FOR UPDATE` before overlap checks to reduce race-condition risk.
- PostgreSQL migration includes exclusion constraint `ex_appointments_provider_no_overlap`:
  - `EXCLUDE USING gist (provider_id WITH =, tstzrange(start_datetime, end_datetime, '[)') WITH &&)`
  - filtered to blocking statuses (`PENDING`, `CONFIRMED`)
- Application-level overlap and slot checks are still retained for clearer API errors.
- New appointments are restricted to `pending` or `confirmed` statuses.
- Reschedule is allowed only for `pending`/`confirmed` and preserves the current status.

## Availability Overlap Rule

- Exact-duplicate availability windows are blocked by DB uniqueness.
- Additional service-layer rule blocks overlapping recurring windows for the same provider + weekday.
- This keeps slot generation deterministic and avoids ambiguous working-hour definitions.

## Customer Identity and Dedup Strategy

- Customer records are deduplicated by `phone_number_normalized` (unique).
- Incoming phone values are normalized to E.164-like `+<digits>` form before insert/update.
- `customer_channel_identities` enforces:
  - unique `(channel, external_user_id)` globally
  - unique `(customer_id, channel)` per customer
- This reduces duplicate-customer risk while keeping Phase 1 model simple.

## Repository Structure

```text
backend/
  app/
    api/routers/
    core/
    db/
    dependencies/
    models/
    repositories/
    schemas/
    services/
    utils/
    workers/
  alembic/
    versions/
  scripts/
  tests/
  Dockerfile
  docker-compose.yml
  pyproject.toml
  .env.example
  README.md
```

## Local Run (Docker)

1. Copy env file:

```bash
cp .env.example .env
```

2. Start services:

```bash
docker compose up --build
```

API:

- `http://localhost:8000`
- health check: `GET /health`
- OpenAPI docs: `http://localhost:8000/docs`

WhatsApp local setup:

- `.env` includes `WHATSAPP_*` keys for webhook flow testing.
- Keep `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and `WHATSAPP_APP_SECRET` empty until real Meta values are available.
- The app can still start locally; outbound WhatsApp sends will fail with a clear configuration error until credentials are set.

## Migrations

From `backend/`:

```bash
alembic upgrade head
```

Create a new migration:

```bash
alembic revision -m "your message"
```

## Seed Data

From `backend/`:

```bash
python -m scripts.seed
```

Seed includes:

- platform admin user
- demo organizations
- membership records
- sample providers/services/customers
- sample channel identity
- availability block
- sample appointment

Demo credentials:

- `admin@bookpoint.local / admin123`
- `owner@demo.local / owner123`

## Tests

From `backend/`:

```bash
pytest
```

## Operations Helpers (Phase 6.4)

Runtime posture:

```bash
python -m scripts.check_runtime
```

Run retention cleanup once:

```bash
python -m scripts.run_cleanup_once
```

Backup / restore helpers:

```bash
./scripts/backup_db.sh [optional-output-file.sql]
./scripts/restore_db.sh <backup-file.sql>
```

PowerShell equivalents:

```powershell
./scripts/backup_db.ps1 [-OutputPath backups\bookpoint.sql]
./scripts/restore_db.ps1 -InputPath backups\bookpoint.sql
```

Initial tests cover:

- auth login/me
- organization creation
- provider creation
- service creation
- availability creation
- availability overlap rejection
- duration/price validation
- slot generation
- appointment creation
- overlap prevention
- reschedule status behavior
- customer phone deduplication (normalized)
- customer channel identity linking

## API Surface (Phase 1)

- `auth`: login, current user
- `organizations`: create/list/get/update
- `organization-members`: add/list/update/deactivate
- `providers`: create/list/get/update/activate/deactivate
- `services`: create/list/get/update/activate/deactivate
  - provider-scoped management: `POST /providers/{provider_id}/services`, `GET /providers/{provider_id}/services`
  - direct service management: `GET /services/{service_id}`, `PATCH /services/{service_id}`, `DELETE /services/{service_id}`
- `customers`: create/list/get/update
- `customer-identities`: create/list
- `provider-availability`: create/list/update/delete
- `provider-time-off`: create/list/update/delete
- `provider-date-overrides`: create/list/update/delete
- `scheduling`: provider slots by date range
- `appointments`: create/list/get/cancel/reschedule
- `admin`: minimal admin-only placeholder endpoints
