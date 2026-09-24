# Sentinel Monitor dashboard

This directory contains the React dashboard for Sentinel Monitor.

## Commands

```powershell
npm install
npm run dev
npm run build
```

The dashboard loads monitored targets and their latest check results from the
FastAPI service. Copy `.env.example` to `.env.local` when the API runs at a
different address, then set `NEXT_PUBLIC_API_BASE_URL` accordingly.

The interface provides loading, validation, API error, retry, empty, and
filtered-empty states. Adding a target persists it through FastAPI, and the
`Check now` action runs a safe check and refreshes the live metrics and alerts.
