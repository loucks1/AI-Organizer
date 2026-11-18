# syntax=docker/dockerfile:1

FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/loucks1/AI-Organizer" \
      org.opencontainers.image.title="AI-Organizer" \
      org.opencontainers.image.description="Drawer inventory capture server"

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/app --shell /bin/sh app \
    && mkdir -p /data/photos \
    && chown -R app:app /data

WORKDIR /app

COPY --chown=1000:1000 schema.sql capture.html server.py mcp_server.py \
    categorize.py search.py inventory_config.py ./

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVENTORY_HOST=0.0.0.0 \
    INVENTORY_PORT=8765 \
    INVENTORY_DB=/data/inventory.db \
    INVENTORY_PHOTOS=/data/photos

USER app

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('INVENTORY_PORT', '8765'), timeout=2)"]

CMD ["python3", "server.py"]
