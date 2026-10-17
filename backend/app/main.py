"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.auth import signing_key
from app.db import DbSession
from app.routers import auth, chat, receipts, stats, webhooks


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    signing_key()  # fail at startup, not at the first login, if JWT_SECRET is missing or weak
    yield


app = FastAPI(title="Receipt Agent", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(receipts.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(webhooks.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: the API process is up."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: DbSession) -> dict[str, str]:
    """Readiness check: the API can reach the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
