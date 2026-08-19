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
        await _add_missing_columns(conn)


async def _add_missing_columns(conn) -> None:
    """Lightweight auto-migration for existing deployments.

    `create_all` only creates tables that don't exist yet — it never alters
    an existing table, so a column added to an ORM model after the database
    file already exists (e.g. on a redeploy with a persistent volume) would
    otherwise cause "no such column" errors at runtime. There's no Alembic
    in this MVP, so instead: for each (table, column, DDL type) we expect,
    add it via ALTER TABLE if missing. Safe to run on every startup — a
    brand-new database already has the column from create_all, so the
    ALTER is simply skipped.
    """
    if "sqlite" not in settings.database_url:
        # This PRAGMA-based check is SQLite-specific; a real Postgres
        # deployment should use proper Alembic migrations instead.
        return

    expected_columns = [
        ("defects", "impact_explanation", "TEXT"),
    ]
    for table, column, ddl_type in expected_columns:
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        if column not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"
            )
