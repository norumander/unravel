"""Shared fixtures for integration tests."""

import io
import tarfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import reset_provider
from app.main import app
from app.sessions.store import session_store


def make_tar_gz(files: dict[str, bytes]) -> bytes:
    """Create an in-memory .tar.gz archive from a filename→content mapping."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clear_state():
    """Clear session store and provider cache before each test."""
    session_store._sessions.clear()
    reset_provider()
    yield
    session_store._sessions.clear()
    reset_provider()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
