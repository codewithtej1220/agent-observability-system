#!/bin/sh
set -e

if [ ! -d /app/artifacts/models ]; then
  if [ "${AOBS_SEED_DEMO:-1}" = "1" ]; then
    echo "No models found: training and seeding demo history (about 2 minutes)..."
    python -m scripts.bootstrap
  else
    echo "No models found: training models only..."
    python -m scripts.bootstrap --no-history
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
