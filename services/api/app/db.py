"""
Async database engine and session dependency.

Production points database_url at Postgres (asyncpg driver) per ADR 0007.
Local dev / tests default to SQLite via aiosqlite so the scaffold runs
without a live Postgres instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Shared declarative base for every model in app/models/."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, closes it after the request."""
    async with async_session_factory() as session:
        yield session


async def create_all_tables() -> None:
    """Dev/test convenience only — real deployments migrate via Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
