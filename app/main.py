"""FastAPI application entry point."""

from fastapi import FastAPI


app = FastAPI(
    title="Online Security Monitoring Tool",
    description="Monitor the availability and basic security posture of authorized targets.",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}

