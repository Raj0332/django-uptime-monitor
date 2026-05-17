# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY app/requirements.txt .
RUN pip install --user --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 app \
    && useradd -u 1000 -g app -m -d /home/app app

COPY --from=builder /root/.local /home/app/.local
COPY --chown=app:app app/ /app/
COPY --chown=app:app docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /tmp/prometheus_multiproc \
    && chown app:app /tmp/prometheus_multiproc

USER app
WORKDIR /app

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc \
    DJANGO_SETTINGS_MODULE=uptime.settings

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
