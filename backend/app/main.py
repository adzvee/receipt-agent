"""FastAPI application entry point."""

from fastapi import FastAPI
from sqlalchemy import text

from app.db import DbSession
from app.routers import chat, receipts

app = FastAPI(title="Receipt Agent", version="0.1.0")
app.include_router(receipts.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: the API process is up."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: DbSession) -> dict[str, str]:
    """Readiness check: the API can reach the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
