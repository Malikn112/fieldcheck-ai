"""
Async SQLAlchemy 2.0 engine & session management.

Provides:
  - `engine`: the async engine, built from `settings.database_url`
  - `AsyncSessionLocal`: session factory
  - `get_db`: FastAPI dependency yielding a request-scoped AsyncSession
  - `init_db`: create tables on startup (fine for SQLite/MVP; use Alembic
    migrations for real production Postgres deployments)
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# `connect_args` is only meaningful for SQLite; ignored otherwise.
_connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug and settings.app_env == "development",
    future=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables if they don't exist. Called on app startup."""
    # Import models so they're registered on Base.metadata before create_all.
    from app.models import asset, defect, inspection  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
