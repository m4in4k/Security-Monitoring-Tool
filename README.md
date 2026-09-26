# Sekuro

Sekuro is a web-based availability and security monitoring platform built with
FastAPI, PostgreSQL, and a responsive React dashboard. It monitors authorized
HTTP and HTTPS targets, records their latest results, and presents availability,
latency, TLS, and basic security-header information in one interface.

> **Current stage:** Phase 2 is implemented and locally verified. Target
> responses are consistent, list queries are paginated and index-backed, running
> checks handle concurrent deletion, and real PostgreSQL integration tests cover
> the database behavior required before scheduled monitoring is introduced.

## Current release

**v0.1.0 — Persistent Monitoring Foundation**

Phase 1 introduced PostgreSQL persistence, target management APIs,
SSRF-protected HTTP monitoring, TLS inspection, security-header checks, and a
dashboard backed by real monitoring results.

See the [v0.1.0 release](https://github.com/m4in4k/Security-Monitoring-Tool/releases/tag/v0.1.0).

## Features

- Responsive desktop and mobile dashboard
- Persistent target creation and management through FastAPI
- Target name, URL, enabled-state, and check-interval validation
- Duplicate-target prevention through normalized URLs
- Manual **Check now** monitoring actions
- HTTP response status and latency collection
- TLS certificate-expiry inspection
- Basic browser security-header checks and scoring
- Request, connection, DNS, and TLS timeouts
- Bounded redirect handling with every redirect revalidated
- SSRF protection for localhost, private networks, metadata endpoints, reserved
  addresses, unsafe hostnames, and non-standard ports
- Dashboard loading, validation, error, retry, and empty states
- Metrics, status distribution, and alerts derived from persisted results

## Architecture

```text
Browser dashboard (React / Vinext)
                 |
                 | HTTP / JSON
                 v
          FastAPI application
                 |
        +--------+--------+
        |        |        |
      HTTP      TLS    Headers
        |        |        |
        +--------+--------+
                 |
          PostgreSQL database
```

## Technology

- **Frontend:** React 19, TypeScript, Tailwind CSS, Vinext
- **Backend:** Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2
- **Database:** PostgreSQL 16, Psycopg 3, Alembic
- **Monitoring:** aiohttp and Python TLS utilities
- **Testing:** Pytest, HTTPX, ESLint, and TypeScript
- **Local infrastructure:** Docker Compose

## Project structure

```text
app/                 FastAPI application and monitoring logic
migrations/          Alembic database migrations
tests/               Backend tests
frontend/            React dashboard
  app/               Dashboard pages and global styles
  components/ui/     Reusable interface components
  lib/               Typed FastAPI client
alembic.ini           Alembic configuration
compose.yaml          Local PostgreSQL service
pyproject.toml        Python package and dependency configuration
```

## Run locally

### Requirements

- Python 3.12 or newer
- Docker Desktop with Docker Compose
- Node.js 22.13 or newer
- npm

### 1. Start PostgreSQL

From the project root:

```powershell
docker compose up -d postgres
docker compose ps
```

The default development database is exposed on `localhost:5432`. Docker stores
its data in the named volume declared in `compose.yaml`.

### 2. Install and configure the backend

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m alembic upgrade head
```

The default database connection matches `compose.yaml`. To override it, use
`.env.example` as a reference and set `DATABASE_URL` in the process environment:

```text
postgresql+psycopg://user:password@host:5432/database
```

### 3. Start the FastAPI backend

```powershell
.venv\Scripts\python.exe -m app.server --reload
```

The API is available at <http://127.0.0.1:8000>. Interactive API documentation
is available at <http://127.0.0.1:8000/docs>.

The `app.server` entrypoint selects a Psycopg-compatible event loop on Windows.

### 4. Start the dashboard

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The dashboard normally opens at <http://localhost:5173> and defaults to the API
at `http://127.0.0.1:8000`.

To use a different API address, copy `frontend/.env.example` to
`frontend/.env.local` and set:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Confirm that the API process is running |
| `GET` | `/targets?limit=20&offset=0` | List a page of targets with their latest persisted check |
| `POST` | `/targets` | Create a monitored target |
| `GET` | `/targets/{id}` | Read one target |
| `PATCH` | `/targets/{id}` | Update selected target fields |
| `DELETE` | `/targets/{id}` | Delete a target and its monitoring history |
| `POST` | `/targets/{id}/checks` | Run and persist one protected monitoring check |

Only HTTP and HTTPS URLs on ports 80 and 443 are accepted. URLs containing
credentials or fragments are rejected.

`GET /targets` accepts `limit` from 1 to 100 and a non-negative `offset`. Its
response contains `items`, `total`, `limit`, and `offset`. List, single-target,
and update responses all include the same `latest_check` field.

## Run a monitoring check

Create a target through the dashboard or `POST /targets`, then run:

```text
POST /targets/{target_id}/checks
```

Manual checks are allowed when a target is disabled. The `enabled` flag controls
future scheduled monitoring; it does not prevent an authorized diagnostic check.
If a target is deleted while a check is running, the check returns `409 Conflict`
and does not leave an orphaned result.

The result records:

- Health status
- HTTP response code
- Response latency
- TLS certificate expiry
- Security-header score and findings
- Final URL and redirect count
- A safe error message when the request fails

## Security model

Sekuro is designed to monitor only systems you own or are explicitly authorized
to test. Every request and redirect destination is checked before connection.

The current protections include:

- Only `http` and `https` protocols
- Only ports 80 and 443
- No credentials embedded in URLs
- DNS resolution with public-address enforcement
- Blocking of loopback, private, link-local, reserved, multicast, and metadata
  addresses
- Blocking of local and internal hostname suffixes
- DNS revalidation by the HTTP resolver
- Manual redirect handling with a maximum of three redirects
- Verified TLS connections
- Bounded DNS, connection, request, and TLS timeouts

These controls reduce SSRF risk, but they do not replace authorization. Do not
monitor third-party systems without explicit permission.

## Verification

The current implementation was verified through the complete flow:

```text
Dashboard -> FastAPI -> PostgreSQL -> monitoring result -> dashboard
```

The verified checks include:

- Real PostgreSQL 16 migrations
- Migration downgrade and re-upgrade
- Target CRUD and duplicate rejection
- Persisted monitoring results
- Cascaded target and result deletion
- Dashboard creation and manual-check flows
- Persistence after browser reload
- Desktop and mobile layouts
- Browser console and error-overlay checks
- 61 passing backend tests, including 6 real PostgreSQL integration tests
- ESLint and TypeScript checks
- Successful frontend production build

## Run validation locally

Backend:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m alembic check
```

Real PostgreSQL integration tests use the isolated, temporary test service:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = "postgresql+psycopg://sekuro_test:sekuro_test@localhost:5433/sekuro_test"
.venv\Scripts\python.exe -m pytest -q -m integration
```

The integration suite refuses to run unless the database name contains `test`.

Frontend:

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

## Development roadmap

- [x] Build the FastAPI application and health endpoint
- [x] Build the responsive monitoring dashboard
- [x] Add PostgreSQL, SQLAlchemy 2, Psycopg 3, and Alembic
- [x] Implement target CRUD with validation and duplicate prevention
- [x] Implement SSRF-protected HTTP monitoring
- [x] Add response-time, TLS-expiry, and security-header checks
- [x] Connect the dashboard to live API and PostgreSQL data
- [x] Verify the complete Phase 1 flow against PostgreSQL 16
- [x] Improve API consistency and latest-result query performance
- [x] Add paginated target listing and deletion-race handling
- [x] Add PostgreSQL integration tests
- [ ] Add historical monitoring results and metrics
- [ ] Add scheduled checks
- [ ] Add persisted incidents and alerts
- [ ] Add authentication and target ownership
- [ ] Add full-stack containers, CI, staging, and deployment

## Responsible use

Use Sekuro only for targets you own or have explicit permission to monitor.
Availability and security-header checks must never be run against unauthorized
systems.

## License

No license has been added yet. Until a license is selected, standard copyright
rules apply and reuse is not automatically permitted.
