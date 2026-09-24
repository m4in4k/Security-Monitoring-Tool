# Sentinel Monitor

Sentinel Monitor is a web-based security and availability monitoring platform. It is a learning-focused full-stack portfolio project built with FastAPI and a modern React dashboard.

> Current stage: the dashboard foundation, FastAPI target API, PostgreSQL persistence, and manual HTTP security checks are implemented. Scheduled checks are the next milestone.

## Preview

The dashboard currently includes:

- Responsive desktop and mobile layouts
- Availability, response-time, alert, and security-score summaries
- Monitored-target status table
- Status filtering and target search
- Add-target workflow with URL normalization
- Healthy, warning, and down states
- Accessible controls and reduced-motion support

Target rows, summary metrics, status distribution, and alerts are calculated
from FastAPI data and the latest persisted monitoring result for each target.

## Architecture

```text
Browser dashboard (React / Vinext)
                 |
                 | HTTP / JSON
                 v
          FastAPI backend
                 |
        +--------+--------+
        |        |        |
      HTTP      TLS     Port checks
        |        |        |
        +--------+--------+
                 |
          PostgreSQL database
```

## Technology

- Frontend: React 19, TypeScript, Tailwind CSS, Vinext
- Backend: Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2
- Database: PostgreSQL with Psycopg 3 and Alembic migrations
- Tests: Pytest and HTTPX
- Planned scheduling: APScheduler

## Project structure

```text
app/                 FastAPI application
migrations/          Alembic database migrations
tests/               Backend tests
frontend/            Web dashboard
  app/               Dashboard pages and styles
  components/ui/     Reusable interface components
pyproject.toml        Python dependencies and configuration
compose.yaml          Local PostgreSQL service
```

## Run locally

### 1. Database and backend

From the project root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
docker compose up -d postgres
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\Activate.ps1
python -m app.server --reload
```

The default local connection is configured for the database in `compose.yaml`.
Set `DATABASE_URL` to override it, using a SQLAlchemy Psycopg URL:

```text
postgresql+psycopg://user:password@host:5432/database
```

Open <http://127.0.0.1:8000/docs> to explore the API documentation.

### Run a monitoring check

Create a target with `POST /targets`, then run and persist one check with:

```text
POST /targets/{target_id}/checks
```

Checks record response status, latency, TLS certificate expiry, redirect details,
and a basic security-header score. Outbound requests have bounded DNS and HTTP
timeouts, a three-redirect limit, verified TLS, and SSRF protection. Targets and
redirects resolving to localhost, private, link-local, reserved, or metadata
addresses are rejected. Only HTTP/HTTPS on ports 80 and 443 are permitted.

### 2. Frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The dashboard defaults to `http://127.0.0.1:8000`. To use another API address,
copy `frontend/.env.example` to `frontend/.env.local` and update
`NEXT_PUBLIC_API_BASE_URL`.

Open the local address shown in the terminal, normally <http://localhost:5173>.

## Run backend tests

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## Learning roadmap

- [x] Create a FastAPI application and health endpoint
- [x] Build the responsive monitoring dashboard
- [x] Add target filtering, search, and a local add-target workflow
- [x] Design the monitored-target API with Pydantic validation
- [x] Add PostgreSQL, SQLAlchemy, and database migrations
- [x] Implement HTTP uptime and response-time checks
- [x] Implement TLS certificate and security-header checks
- [ ] Add scheduled checks, alerts, and historical results
- [x] Connect the dashboard to live API data
- [ ] Add authentication, Docker, and deployment

## Responsible use

Only monitor or scan systems you own or have explicit permission to test. Port and security checks must never be used against unauthorized systems.
