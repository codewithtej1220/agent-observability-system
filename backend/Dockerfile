FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN useradd -m -u 1000 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p /app/artifacts /app/data && chown -R app:app /app/artifacts /app/data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=240s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# On first start (no trained model yet) the entrypoint trains the models and,
# if AOBS_SEED_DEMO=1, replays simulated history so the dashboard has data.
CMD ["sh", "docker-entrypoint.sh"]
