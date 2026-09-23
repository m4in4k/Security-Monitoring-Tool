# Sentinel Monitor

Sentinel Monitor is a web-based security and availability monitoring platform. It is a learning-focused full-stack portfolio project built with FastAPI and a modern React dashboard.

> Current stage: the dashboard foundation and FastAPI health endpoint are working locally. Monitoring checks and persistent storage are the next milestone.

## Preview

The dashboard currently includes:

- Responsive desktop and mobile layouts
- Availability, response-time, alert, and security-score summaries
- Monitored-target status table
- Status filtering and target search
- Add-target workflow with URL normalization
- Healthy, warning, and down states
- Accessible controls and reduced-motion support

The initial target data is demonstrative. It will be replaced by results from the FastAPI monitoring service.

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
- Backend: Python 3.12, FastAPI, Uvicorn
- Tests: Pytest and HTTPX
- Planned persistence: PostgreSQL and SQLAlchemy
- Planned scheduling: APScheduler

## Project structure

```text
app/                 FastAPI application
tests/               Backend tests
frontend/            Web dashboard
  app/               Dashboard pages and styles
  components/ui/     Reusable interface components
pyproject.toml        Python dependencies and configuration
```

## Run locally

### 1. Backend

From the project root:

```powershell
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> to explore the API documentation.

### 2. Frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local address shown in the terminal, normally <http://localhost:5173>.

## Run backend tests

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## Learning roadmap

- [x] Create a FastAPI application and health endpoint
- [x] Build the responsive monitoring dashboard
- [x] Add target filtering, search, and a local add-target workflow
- [ ] Design the monitored-target API with Pydantic validation
- [ ] Add PostgreSQL, SQLAlchemy, and database migrations
- [ ] Implement HTTP uptime and response-time checks
- [ ] Implement TLS certificate and security-header checks
- [ ] Add scheduled checks, alerts, and historical results
- [ ] Connect the dashboard to live API data
- [ ] Add authentication, Docker, and deployment

## Responsible use

Only monitor or scan systems you own or have explicit permission to test. Port and security checks must never be used against unauthorized systems.
