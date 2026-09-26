# Sekuro dashboard

This directory contains the React dashboard for Sekuro.

## Commands

```powershell
npm install
npm run dev
npm run build
```

The dashboard uses Clerk for sign-in and sends Clerk's short-lived session token
to FastAPI as a bearer token. FastAPI independently validates that token before
returning the signed-in user's targets.

Copy `.env.example` to `.env.local`, then configure
`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, and
`CLERK_SECRET_KEY`. The matching Clerk session token must include
`"aud": "sekuro-api"`; backend identity settings live in the repository-root
`.env` file.

The interface provides loading, validation, API error, retry, empty, and
filtered-empty states. Adding a target persists it through FastAPI, and the
`Check now` action runs a safe check and refreshes the live metrics and alerts.
Targets belonging to other users never enter the dashboard response.
