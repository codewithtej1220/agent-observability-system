"""Model registry: holds the active detection engine and the live policy.

Artifacts layout:
    artifacts/models/<version>/engine.pkl     fitted engine (all detection models)
    artifacts/models/<version>/metrics.json   held-out evaluation report
    artifacts/policy.json                     live bandit state (updated on every reward)
    artifacts/policy_warmstart.json           offline warm-start report
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

from ml.bandit import LinUCBPolicy
from ml.engine import Engine

from ..config import get_settings
from ..orm import ModelVersion

log = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


class Registry:
    def __init__(self, artifacts_dir: Path):
        self.dir = artifacts_dir
        self.lock = threading.RLock()
        self.engine: Optional[Engine] = None
        self.policy: Optional[LinUCBPolicy] = None
        self.retraining = False

    # paths ----------------------------------------------------------------
    def model_dir(self, version: str) -> Path:
        return self.dir / "models" / version

    @property
    def policy_path(self) -> Path:
        return self.dir / "policy.json"

    @property
    def warmstart_path(self) -> Path:
        return self.dir / "policy_warmstart.json"

    # loading --------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.engine is not None and self.policy is not None

    def load(self, db: Session) -> None:
        active = db.query(ModelVersion).filter(ModelVersion.active.is_(True)).first()
        if active is None:
            log.warning("No active model version. Run `python -m scripts.bootstrap` first.")
            return
        path = self.model_dir(active.version) / "engine.pkl"
        if not path.exists():
            log.error("Active model %s has no artifact at %s", active.version, path)
            return
        with self.lock:
            self.engine = Engine.load(str(path))
            if self.policy_path.exists():
                self.policy = LinUCBPolicy.from_dict(json.loads(self.policy_path.read_text(encoding="utf-8")))
            else:
                self.policy = LinUCBPolicy()
        log.info("Loaded model %s and policy (%d updates)", active.version, self.policy.n_updates)

    def save_engine(self, engine: Engine, metrics: Dict) -> None:
        d = self.model_dir(engine.version)
        d.mkdir(parents=True, exist_ok=True)
        engine.save(str(d / "engine.pkl"))
        _atomic_write_json(d / "metrics.json", metrics)

    def activate(self, engine: Engine) -> None:
        with self.lock:
            self.engine = engine

    def save_policy(self) -> None:
        with self.lock:
            if self.policy is not None:
                _atomic_write_json(self.policy_path, self.policy.to_dict())

    def set_policy(self, policy: LinUCBPolicy, warmstart_report: Optional[Dict] = None) -> None:
        with self.lock:
            self.policy = policy
            self.save_policy()
            if warmstart_report is not None:
                _atomic_write_json(self.warmstart_path, warmstart_report)

    def metrics(self, version: str) -> Optional[Dict]:
        p = self.model_dir(version) / "metrics.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def warmstart_report(self) -> Optional[Dict]:
        p = self.warmstart_path
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


registry = Registry(get_settings().artifacts_dir)
