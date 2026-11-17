#!/bin/sh
set -e

if [ ! -d /app/artifacts/models ]; then
  echo "No models found: downloading real agent traces and training (several minutes)..."
  python -m scripts.fetch_real_traces
  if [ "${AOBS_IMPORT_PUBLIC_RUNS:-0}" != "0" ]; then
    python -m scripts.bootstrap --skip-robustness --import-runs "${AOBS_IMPORT_PUBLIC_RUNS}"
  else
    python -m scripts.bootstrap --skip-robustness
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
