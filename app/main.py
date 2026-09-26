"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.targets import router as targets_router
from app.users import router as users_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release pooled database connections during application shutdown."""
    yield
    await engine.dispose()


app = FastAPI(
    title="Sekuro API",
    description="Sekuro monitors the availability and basic security posture of authorized targets.",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(targets_router)
app.include_router(users_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}

