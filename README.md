# Sekuro

Sekuro is a web-based availability and security monitoring platform built with
FastAPI, PostgreSQL, and a responsive React dashboard. It monitors authorized
HTTP and HTTPS targets, records their latest results, and presents availability,
latency, TLS, and basic security-header information in one interface.

> **Current stage:** Phase 3 adds Clerk authentication, FastAPI JWT verification,
> local user provisioning, and strict per-user target ownership. Phase 2's
> paginated, index-backed target API remains the foundation for the protected
> multi-user dashboard.

## Current release

**v0.3.0 — Multi-User Authentication and Ownership**

Phase 3 adds Clerk authentication, independently verified FastAPI bearer
tokens, automatic local-user provisioning, strict per-user target ownership,
protected monitoring operations, and PostgreSQL authorization tests.

See the [v0.3.0 release](https://github.com/m4in4k/Security-Monitoring-Tool/releases/tag/v0.3.0).

## Features

- Responsive desktop and mobile dashboard
- Clerk sign-in with independently verified FastAPI bearer tokens
- Per-user target isolation and per-user duplicate prevention
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
Browser dashboard (React / Vinext + Clerk)
                 |
                 | Clerk bearer token + HTTP / JSON
                 v
          FastAPI application
                 |
          JWT / JWKS validation
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
- **Identity:** Clerk sessions, RS256 JWTs, and JWKS verification
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
`.env.example` as a reference. Copy it to `.env`, then configure the database
and Clerk values:

```text
DATABASE_URL=postgresql+psycopg://user:password@host:5432/database
AUTH_ISSUER=https://your-clerk-domain.clerk.accounts.dev
AUTH_AUDIENCE=sekuro-api
AUTH_AUTHORIZED_PARTIES=http://localhost:5173,http://127.0.0.1:5173
```

In the Clerk dashboard, customize the session token claims to include the API
audience and optional profile values:

```json
{
  "aud": "sekuro-api",
  "email": "{{user.primary_email_address}}",
  "name": "{{user.first_name}}"
}
```

FastAPI validates the token signature through Clerk's JWKS endpoint and checks
its issuer, audience, expiry, signing algorithm, and authorized frontend origin.

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

Copy `frontend/.env.example` to `frontend/.env.local`, then set the API address
and the Clerk keys for your development application:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_replace_me
CLERK_SECRET_KEY=sk_test_replace_me
```

The dashboard remains on a setup screen until Clerk is configured. Secret keys,
local environment files, and bearer tokens must never be committed.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Confirm that the API process is running |
| `GET` | `/users/me` | Return the authenticated local user |
| `GET` | `/targets?limit=20&offset=0` | List a page of targets with their latest persisted check |
| `POST` | `/targets` | Create a monitored target |
| `GET` | `/targets/{id}` | Read one target |
| `PATCH` | `/targets/{id}` | Update selected target fields |
| `DELETE` | `/targets/{id}` | Delete a target and its monitoring history |
| `POST` | `/targets/{id}/checks` | Run and persist one protected monitoring check |

`GET /health` is public. Every user and target endpoint requires a valid bearer
token. Target identifiers are always resolved together with the current user's
ID; inaccessible targets return `404` without revealing another user's data.

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

- RS256 signature, issuer, audience, expiry, and authorized-party validation
- Automatic local-user provisioning from a validated Clerk subject
- Ownership checks on every target list, read, update, delete, and check query
- Per-owner URL uniqueness at the PostgreSQL constraint level
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
- Authentication tests for expired, malformed, wrong-issuer, wrong-audience,
  wrong-origin, and unsupported-algorithm tokens
- Two-user authorization tests for list, read, update, delete, and manual checks
- Real PostgreSQL integration coverage for ownership and user provisioning
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
- [x] Add authentication and target ownership
- [ ] Add historical monitoring results and metrics
- [ ] Add scheduled checks
- [ ] Add persisted incidents and alerts
- [ ] Add full-stack containers, CI, staging, and deployment

## Responsible use

Use Sekuro only for targets you own or have explicit permission to monitor.
Availability and security-header checks must never be run against unauthorized
systems.

## License

No license has been added yet. Until a license is selected, standard copyright
rules apply and reuse is not automatically permitted.
