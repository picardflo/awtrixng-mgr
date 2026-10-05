"""Isolate each test run in its own data directory.

Must run before any app.* import, since the settings and the SQLAlchemy engine
are resolved at import time.
"""

import os
import tempfile

os.environ["AWTRIXNG_DATA_DIR"] = tempfile.mkdtemp(prefix="awtrixng-tests-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture
def client():
    """Fresh database per test: wipe everything, the lifespan replays migrations."""
    from sqlmodel import SQLModel

    from app.db.session import engine

    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    with TestClient(create_app()) as test_client:
        yield test_client
