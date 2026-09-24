"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.targets import router as targets_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release pooled database connections during application shutdown."""
    yield
    await engine.dispose()


app = FastAPI(
    title="Online Security Monitoring Tool",
    description="Monitor the availability and basic security posture of authorized targets.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(targets_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}

