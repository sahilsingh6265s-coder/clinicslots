# ClinicSlot: Doctor Appointment Booking API

![CI](https://github.com/sahilsingh6265s-coder/clinicslots/actions/workflows/ci.yml/badge.svg)

A backend for booking doctor appointments. Patients see real availability and book instantly, doctors manage their day, and admins get a dashboard.

**The problem:** many clinics still book by phone or on paper, which causes double bookings, long waits and no records. The interesting engineering question is: *what happens when two patients click "book 10:00 AM" at the same instant?* ClinicSlot answers that in the database, not in application code, and proves it with a concurrency test.

> **Portfolio positioning:** ClinicSlot is a healthcare operations and capacity-allocation project. It is not a warehouse or logistics system, but it demonstrates the same supply-chain fundamentals: matching demand to constrained capacity, preventing over-allocation, preserving an audit trail, and turning operational events into management metrics.

<details open>
<summary><strong>Project tour</strong></summary>

- [What the system does](#what-the-system-does)
- [End-to-end workflow](#end-to-end-workflow)
- [Why this is a strong operations project](#why-this-is-a-strong-operations-project)
- [Run it locally](#quick-start)
- [Try the API interactively](#interactive-api-walkthrough)
- [Architecture and data model](#architecture)
- [Reliability and security proof](#design-decisions)

</details>

## What the system does

ClinicSlot treats appointment time as a finite operational resource:

1. A doctor publishes recurring working windows.
2. The platform calculates bookable slots from those windows.
3. A patient selects a slot and submits a booking request.
4. The database atomically accepts one winner if requests race for the same capacity.
5. Doctors update fulfillment status, while admins monitor demand, cancellations and utilization.

The result is a complete workflow from **capacity planning → allocation → fulfillment → reporting**, exposed through a documented FastAPI service.

## End-to-end workflow

```mermaid
sequenceDiagram
    autonumber
    participant P as Patient
    participant API as FastAPI API
    participant S as Services
    participant DB as PostgreSQL
    participant D as Doctor
    participant A as Admin

    P->>API: Sign up / log in
    API->>DB: Verify user and issue JWT
    D->>API: Publish weekly availability
    API->>S: Validate schedule
    S->>DB: Save availability
    P->>API: Request slots for a date
    API->>S: Generate slots minus confirmed bookings
    S->>DB: Read schedule and appointments
    DB-->>P: Return real-time free slots
    P->>API: Book a slot
    API->>S: Validate ownership, time and cutoff
    S->>DB: Insert confirmed appointment
    DB-->>P: Confirm booking or return 409 if already taken
    D->>API: Mark completed or no-show
    A->>API: Request operational statistics
    API->>DB: Read appointment history
    DB-->>A: Return daily, doctor and status metrics
```

<details>
<summary><strong>Role-by-role journey</strong></summary>

| Actor | Workflow | Operational outcome |
|---|---|---|
| Patient | Register → discover specialty → view live slots → book/cancel/reschedule → review history | Less friction and fewer missed or duplicate bookings |
| Doctor | Configure weekly hours → view daily schedule → complete/no-show appointments | A reliable working-day queue |
| Admin | Create/deactivate doctors → inspect daily and per-doctor statistics | Capacity visibility and accountable operations |

</details>

## Why this is a strong operations project

This is a compelling supply-chain-adjacent portfolio project because it shows more than CRUD:

| Operations concept | ClinicSlot implementation | Why it matters |
|---|---|---|
| Constrained capacity | Doctor time windows become bookable slots | Prevents selling unavailable capacity |
| Demand allocation | Patients compete for the same finite slot | Models real allocation pressure |
| Transaction integrity | PostgreSQL partial unique index allows one confirmed winner | Eliminates double booking under concurrency |
| Flexibility and recovery | Cancellation and atomic rescheduling release or move demand | Keeps capacity reusable without losing history |
| Fulfillment tracking | Confirmed, cancelled, completed and no-show states | Separates planned work from delivered work |
| Operational intelligence | Admin statistics by day, time, doctor and status | Supports staffing and utilization decisions |
| Traceability | Soft cancellation and deactivation preserve records | Makes decisions auditable |

It is a strong demonstration of production thinking: business rules are separated from HTTP handlers, security is role-based, migrations are versioned, and CI runs the test suite against PostgreSQL.

## Live demo

> **API + interactive docs:** https://YOUR-SERVICE-NAME.onrender.com/docs  *(replace with your Render URL)*

Hosted on free tiers, so the **first request after ~15 minutes idle takes up to a minute** while the server wakes up (and a few extra seconds while the database resumes). After that it is fast. Log in with a demo account from the table below.

## Features

| Role | Can do |
|---|---|
| **Patient** | Sign up, log in, browse doctors by specialty, see free slots for a date, book, cancel, reschedule, view paginated history |
| **Doctor** | Set a weekly schedule, view a day's appointments, mark appointments completed or no-show |
| **Admin** | Create and remove doctors, view stats (bookings per day, busiest times, cancellations, per-doctor numbers) |

## Tech stack

Python 3.13, **FastAPI**, **PostgreSQL**, SQLAlchemy 2.0, Alembic (migrations), Pydantic, JWT + bcrypt, pytest, Docker, GitHub Actions.

## Architecture

```mermaid
flowchart LR
    C[Client / Swagger UI] -->|HTTP + JWT| R[Routers<br/>HTTP only]
    R --> D[Dependencies<br/>auth + role checks]
    R --> S[Services<br/>business rules]
    S --> M[SQLAlchemy models]
    M --> DB[(PostgreSQL<br/>constraints enforce<br/>the hard rules)]
```

Routers only translate HTTP to function calls and exceptions to status codes. All rules (slot validation, cancellation cut-off, status transitions) live in `services/`, so they can be tested without HTTP.

## Interactive API walkthrough

After starting the service, open **[Swagger UI](http://localhost:8000/docs)**:

<details>
<summary><strong>Run a complete demo in Swagger UI</strong></summary>

1. `POST /auth/login` with a seeded patient account and copy the JWT.
2. Click **Authorize**, enter the token, and select **Authorize**.
3. `GET /doctors` to find a doctor.
4. `GET /doctors/{id}/slots?date=YYYY-MM-DD` to inspect calculated capacity.
5. `POST /appointments` with a returned `slot_start` to allocate one slot.
6. `GET /me/appointments` to confirm the patient's operational history.
7. Log in as a doctor and use `/doctor/schedule` plus the status endpoint to complete the workflow.
8. Log in as an admin and call `/admin/stats` to see the resulting demand and fulfillment metrics.

The OpenAPI page is generated from the same schemas and routes used by the application, so it is both documentation and a live integration surface.

</details>

<details>
<summary><strong>What happens when two patients book simultaneously?</strong></summary>

Both requests may read the slot as available, but only one database insert can satisfy the partial unique index for a confirmed appointment. The winner receives success; the other receives `409 Conflict`. The concurrency test fires eight simultaneous requests and verifies that exactly one succeeds. This is safer than relying on a check-then-insert sequence in Python.

</details>

## Data model

```mermaid
erDiagram
    USERS ||--o| DOCTORS : "has profile"
    DOCTORS ||--o{ AVAILABILITY : "works"
    DOCTORS ||--o{ APPOINTMENTS : "receives"
    USERS ||--o{ APPOINTMENTS : "books"

    USERS {
        int id PK
        string name
        string email UK
        string password_hash
        string role "patient / doctor / admin"
    }
    DOCTORS {
        int id PK
        int user_id FK
        string specialty
        int slot_minutes
        bool is_active
    }
    AVAILABILITY {
        int id PK
        int doctor_id FK
        int weekday "0 = Monday"
        time start_time
        time end_time
    }
    APPOINTMENTS {
        int id PK
        int patient_id FK
        int doctor_id FK
        datetime slot_start "stored in UTC"
        string status "confirmed / cancelled / completed / no_show"
    }
```

## Quick start

### With Docker (one command)

```bash
docker compose up --build        # starts PostgreSQL + the API and applies migrations
docker compose exec api python -m scripts.seed    # optional: fake demo data
```

### Without Docker

```bash
python -m venv .venv
.venv\Scripts\activate           # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
# create an empty PostgreSQL database matching DATABASE_URL in .env, then:
alembic upgrade head
python -m scripts.seed           # optional: fake demo data
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for interactive API docs. Click **Authorize** and log in (the email goes in the `username` field).

### Demo accounts (after seeding)

Seeded patient and doctor accounts use the password `Password123`.

| Role | Email |
|---|---|
| Admin | `admin@clinicslot.demo` (see the note below about its password) |
| Doctor | `doctor1@clinicslot.demo` ... `doctor10@clinicslot.demo` |
| Patient | `patient1@clinicslot.demo` ... `patient20@clinicslot.demo` |

The admin uses `Password123` too by default, which is fine locally. For a **public** demo, seed with a private admin password so only you can use the admin endpoints:

```bash
python -m scripts.seed --private-admin      # asks for the password (hidden input)
# or, for non-interactive runs, set the SEED_ADMIN_PASSWORD environment variable
```

To create your own admin instead: `python -m scripts.create_admin`.
`python -m scripts.seed --reset` wipes the database and reseeds (it asks you to confirm).

## API overview

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/signup` | anyone | Register as a patient |
| POST | `/auth/login` | anyone | Get a JWT |
| GET | `/auth/me` | any user | Current user |
| GET | `/doctors?specialty=` | any user | Browse doctors |
| GET | `/doctors/{id}/slots?date=` | any user | Free slots for a day |
| POST | `/appointments` | patient | Book a slot |
| PATCH | `/appointments/{id}` | patient | Reschedule (atomic) |
| DELETE | `/appointments/{id}` | patient | Cancel (soft) |
| GET | `/me/appointments?page=&page_size=&status=` | patient | Paginated history |
| GET / PUT | `/doctor/availability` | doctor | View / replace weekly schedule |
| GET | `/doctor/schedule?date=` | doctor | The day's appointments |
| PATCH | `/doctor/appointments/{id}/status` | doctor | Mark completed / no_show |
| POST | `/admin/doctors` | admin | Create a doctor |
| DELETE | `/admin/doctors/{id}` | admin | Deactivate a doctor |
| GET | `/admin/stats?from_date=&to_date=` | admin | Dashboard numbers |

## Deployment

The API runs on **Render** (free web service) and the database on **Neon** (free PostgreSQL). Render's own free database expires after 30 days, which is why the database lives elsewhere.

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

| Environment variable | Value |
|---|---|
| `DATABASE_URL` | the Neon connection string (the `postgresql://...` form is fine; the app adds the driver name) |
| `SECRET_KEY` | a long random string, 32+ characters. With `ENVIRONMENT=production` the app **refuses to start** if it is missing or weak |
| `ENVIRONMENT` | `production` |
| `PYTHON_VERSION` | `3.13.5` |

`render.yaml` contains the same settings as a Render Blueprint. Migrations run automatically on every deploy because they are part of the start command.

To load demo data into the hosted database, run the seed **from your own computer** with `DATABASE_URL` pointing at the hosted database (see the seed section above), then remove that variable again.

## Testing

```bash
pytest
```

By default the tests use a throwaway in-memory SQLite database, so no setup is needed. To run them against real PostgreSQL, point `TEST_DATABASE_URL` at an **empty test database** (its tables are dropped and recreated for every test):

```bash
TEST_DATABASE_URL=postgresql+psycopg2://clinic:clinic@localhost:5432/clinicslot_test pytest
```

GitHub Actions runs the full suite against PostgreSQL on every push, and also fails the build if the models and the Alembic migrations disagree (`alembic check`).

## Design decisions

1. **No double booking, enforced by the database.** A partial unique index on `(doctor_id, slot_start) WHERE status = 'confirmed'` lets exactly one booking win a race. The code just inserts and turns the integrity error into `409`. A "check if free, then insert" in Python has a race window where two requests both pass the check. A concurrency test fires 8 simultaneous bookings and asserts exactly one succeeds.
2. **Why a *partial* index?** A plain unique constraint would also count cancelled rows, so a cancelled slot could never be rebooked. Restricting it to confirmed rows keeps history without blocking the slot.
3. **Slots are calculated, not stored.** Free slots come from the doctor's weekly windows minus existing appointments. This keeps the data small, and an availability change applies immediately. The generator is a pure function, so it is easy to unit-test.
4. **Timezones.** Working hours are wall-clock times in the clinic's timezone (`CLINIC_TIMEZONE`, default `Asia/Kolkata`); appointments are stored in UTC. Conversion happens at the edges, and API requests must include a UTC offset (naive times are rejected).
5. **Atomic rescheduling.** The old appointment is cancelled and the new one created in one transaction. If the new slot is taken, everything rolls back and the patient keeps the original.
6. **Soft cancel and soft delete.** Cancelled appointments keep their row (history), and removing a doctor deactivates them. Past appointments and stats stay consistent. A doctor with upcoming appointments cannot be removed.
7. **Layered code.** Routers (HTTP) -> services (rules) -> models (data). Rules can be tested without HTTP.
8. **Security basics.** Passwords are hashed with bcrypt, JWTs expire, roles are checked in a reusable dependency, self-signup can only create patients, and other users' appointments return `404` rather than `403` so ids are not leaked.
9. **Fast tests, real-database confidence.** Day-to-day tests run on SQLite; CI runs the same suite on PostgreSQL, where the concurrency guarantee actually matters.

## Project structure

```
app/
  core/        config, database session, security (hashing, JWT), auth dependencies
  models/      SQLAlchemy tables
  schemas/     Pydantic request / response models
  services/    business logic (booking, slots, doctors, schedule, stats)
  routers/     HTTP endpoints
alembic/       database migrations
scripts/       seed.py (demo data), create_admin.py
tests/         unit, API and concurrency tests
.github/       CI workflow
render.yaml    Render deployment settings (optional Blueprint)
```

## Screenshots

Add screenshots of the interactive docs and the stats endpoint here, for example in `docs/screenshots/`.

## Known limitations and ideas

- No email notifications and no frontend yet.
- Free-tier hosting: the server sleeps when idle, so the first request can be slow.
- JWTs cannot be revoked before they expire (no refresh tokens or blocklist).
- No rate limiting on login.
- Admin stats are aggregated in Python after loading the date range. That is fine at clinic scale; at larger scale this would move into SQL.
- A removed doctor's email stays reserved, and there is no "reactivate" endpoint.
