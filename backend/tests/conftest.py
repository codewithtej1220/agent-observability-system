import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolated database and artifacts for the whole test session. Must be set
# before the app modules are imported (settings and engine are created on import).
_TMP = tempfile.mkdtemp(prefix="aobs-test-")
os.environ["AOBS_DATABASE_URL"] = f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
os.environ["AOBS_ARTIFACTS_DIR"] = str(Path(_TMP, "artifacts"))
os.environ["AOBS_DEV_API_KEY"] = "test-key"
os.environ["AOBS_AUTO_RETRAIN_EVERY"] = "0"
os.environ["AOBS_BACKGROUND_JOBS"] = "false"
os.environ["AOBS_GOOGLE_CLIENT_ID"] = "test-client"
os.environ["AOBS_GOOGLE_CLIENT_SECRET"] = "test-secret"
# Fixed test-only encryption key (not a real secret).
os.environ["AOBS_SECRET_KEY"] = "Lx2u7mXo9oHqM0JX8bUOz4dxsPJ4y6mFv0z0Sm7m0vY="

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.bandit import LinUCBPolicy  # noqa: E402
from ml.simulator import generate_dataset, generate_run, AGENT_BY_ID  # noqa: E402
from ml.training import train_engine  # noqa: E402


@pytest.fixture(scope="session")
def small_engine():
    train = generate_dataset(600, seed=11, balanced=True)
    val = generate_dataset(250, seed=12)
    return train_engine(train, val, version="test")


@pytest.fixture(scope="session")
def client(small_engine):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.registry import registry

    with TestClient(app) as c:
        from app.db import SessionLocal
        from scripts.bootstrap import ensure_demo_workspace

        db = SessionLocal()
        ensure_demo_workspace(db)
        db.close()
        registry.activate(small_engine)
        registry.policy = LinUCBPolicy()
        c.headers.update({"X-API-Key": "test-key"})
        yield c


@pytest.fixture
def make_run():
    import random

    def _make(label="healthy", agent="support-bot", seed=0):
        return generate_run(random.Random(seed), agent=AGENT_BY_ID[agent], label=label)

    return _make


@pytest.fixture
def new_user(client):
    """Factory: sign up a fresh user in an isolated TestClient (own cookie jar)."""
    import uuid

    from fastapi.testclient import TestClient

    from app.main import app

    made = []

    def _make(email=None, password="correct-horse-9"):
        c = TestClient(app)
        c.headers.update({"X-Requested-With": "aobs"})
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        r = c.post("/api/auth/signup", json={"email": email, "password": password, "name": "Test User"})
        assert r.status_code == 200, r.text
        made.append(c)
        return c, email

    return _make
