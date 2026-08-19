"""Shared pytest fixtures — isolated test DB, uploads dir, and an async
HTTP client wired to the FastAPI app via ASGI transport (no real network).

IMPORTANT: the environment variables that redirect the app at a throwaway
SQLite DB / uploads dir / mock vision mode are set at *module import time*
(below), not inside a fixture. `app/config.py` and `app/database.py` build
module-level singletons (`settings`, `engine`) the moment they are first
imported, and pytest imports every test module's top-level imports during
collection — before any fixture (even session-scoped ones) has run. If
these env vars were only set inside a fixture, any test module that
imports app code at module level (e.g. `from app.services.storage_service
import ...`) would trigger `app.config` to initialize against the *real*
`.env` / default DB before the fixture ever got a chance to override it,
silently leaking test data into the real `fieldcheck.db`.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="fieldcheck_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DIR}/test.db"
os.environ["UPLOAD_DIR"] = f"{_TMP_DIR}/uploads"
os.environ["REPORT_OUTPUT_DIR"] = f"{_TMP_DIR}/reports"
os.environ["VISION_MOCK_MODE"] = "true"
os.environ["USE_CELERY"] = "false"
os.environ["MAX_UPLOAD_SIZE_MB"] = "15"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_dir():
    yield
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def client():
    from app.database import init_db
    from app.main import app

    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (640, 480), color=(120, 140, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_png_bytes() -> bytes:
    img = Image.new("RGB", (640, 480), color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
