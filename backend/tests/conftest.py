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
os.environ["AOBS_API_KEYS"] = "test-key"
os.environ["AOBS_AUTO_RETRAIN_EVERY"] = "0"

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
