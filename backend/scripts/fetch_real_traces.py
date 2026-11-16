"""Download the real agent traces used for training (about 184 MB).

    python -m scripts.fetch_real_traces        (from backend/)

Source: https://huggingface.co/datasets/nebius/SWE-agent-trajectories (CC BY 4.0).
Saves two Parquet shards (~13,000 SWE-agent runs) to backend/data/real_traces/.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.training import DATA_DIR  # noqa: E402
from ml import real_traces  # noqa: E402

BASE = f"https://huggingface.co/datasets/{real_traces.DATASET}/resolve/main/"


def main() -> None:
    out_dir = real_traces.data_dir(DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    for shard, path in zip(real_traces.SHARDS, real_traces.shard_paths(DATA_DIR)):
        if path.exists():
            print(f"{path.name}: already downloaded")
            continue
        tmp = path.with_suffix(".part")
        print(f"Downloading {shard} ...")
        with urllib.request.urlopen(BASE + shard, timeout=60) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.replace(path)
        print(f"{path.name}: {path.stat().st_size / 1e6:.0f} MB")
    print(f"Done. Data: {real_traces.DATASET} ({real_traces.LICENSE}).")


if __name__ == "__main__":
    main()
