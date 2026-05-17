# Django Uptime Monitor

A self-hosted HTTP uptime monitoring application. Users add URLs, background workers ping them on schedule, and the dashboard shows current status, uptime percentages, response-time history, and incidents.

## Architecture

```
Browser ──────────────────────────────────────┐
          HTTP                                 │
          ▼                                    │
    ┌──────────┐   SELECT/INSERT   ┌────────┐  │
    │   web    │──────────────────▶│  db    │  │
    │(Gunicorn)│                   │(PG 16) │  │
    │          │◀── cache/session ─│        │  │
    └────┬─────┘                   └────────┘  │
         │ broker/result                        │
         ▼                                      │
    ┌──────────┐                   ┌────────┐  │
    │  redis   │◀─ enqueue ───────▶│ worker │  │
    │  (7)     │                   │(Celery)│  │
    └────▲─────┘                   └───┬────┘  │
         │                             │        │
    ┌────┴─────┐                       │ HTTP   │
    │   beat   │                       ▼        │
    │(scheduler│              external URLs     │
    └──────────┘                                │
```

## Quick Start

```bash
# 1. Clone and enter the project
cd django-uptime-monitor

# 2. Create your .env file
cp .env.example .env

# 3. Generate a secure SECRET_KEY and paste it into .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 4. Start all services
make up

# 5. Create an admin user
make superuser

# 6. Open http://localhost:8000/accounts/signup/ to register a regular user
# 7. Add a site (e.g. https://www.google.com with 60s interval)
# 8. Within ~60s the dashboard card turns green
```

## Project Layout

```
django-uptime-monitor/
├── app/                  Django project root
│   ├── monitor/          Main app (models, views, tasks, templates)
│   ├── uptime/           Django config (settings, celery, wsgi)
│   ├── manage.py
│   └── requirements*.txt
├── docker/               Dockerfile + entrypoint
├── docker-compose.yml
├── .env.example
└── Makefile
```

## Endpoints Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | — | Redirects to `/sites/` |
| GET | `/sites/` | Login | Dashboard (all sites) |
| GET | `/sites/?partial=1` | Login | HTMX partial grid |
| GET | `/sites/add/` | Login | Add-site form |
| POST | `/sites/add/` | Login | Create site |
| GET | `/sites/<id>/` | Login (owner) | Site detail |
| POST | `/sites/<id>/delete/` | Login (owner) | Delete site |
| POST | `/sites/<id>/toggle/` | Login (owner) | Pause/resume |
| GET | `/sites/<id>/card/` | Login (owner) | HTMX card partial |
| GET | `/accounts/signup/` | — | Registration |
| GET/POST | `/accounts/login/` | — | Login |
| POST | `/accounts/logout/` | — | Logout |
| GET | `/healthz/` | — | Liveness probe |
| GET | `/readyz/` | — | Readiness probe |
| GET | `/metrics/` | — | Prometheus metrics |
| GET/POST | `/api/sites/` | Token | List/create sites |
| GET/PATCH/DELETE | `/api/sites/<id>/` | Token | Site detail |
| GET | `/api/sites/<id>/checks/` | Token | Paginated checks |
| GET | `/api/sites/<id>/incidents/` | Token | Incidents |
| POST | `/api/auth/token/` | — | Obtain API token |

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SECRET_KEY` | — | Yes | Django secret key |
| `DEBUG` | `False` | No | Enable debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | No | Comma-separated allowed hosts |
| `DATABASE_URL` | — | Yes | Postgres DSN |
| `REDIS_URL` | — | Yes | Redis DSN |
| `POSTGRES_USER` | `uptime` | No | Postgres user (compose) |
| `POSTGRES_PASSWORD` | `uptime` | No | Postgres password (compose) |
| `POSTGRES_DB` | `uptime` | No | Postgres database (compose) |
| `PROMETHEUS_MULTIPROC_DIR` | `/tmp/prometheus_multiproc` | No | Multiprocess metrics dir |

## Metrics Exposed

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `site_check_total` | Counter | `status` (up/down/error) | Total HTTP checks performed |
| `site_check_duration_seconds` | Histogram | — | Duration of each check |
| `dispatch_checks_enqueued_total` | Counter | — | Tasks enqueued by scheduler |
| `incidents_opened_total` | Counter | — | Incidents opened |
| `incidents_closed_total` | Counter | — | Incidents closed |
| `current_open_incidents` | Gauge | — | Currently open incidents |
| `sites_active_total` | Gauge | — | Active monitored sites |

Plus all default Django and Celery metrics from django-prometheus.

## Running Tests

```bash
make test
# or directly:
cd app && pytest --cov=monitor --cov-report=term-missing -v
```

## Tech Decisions

- **Django over FastAPI**: Built-in admin, ORM, auth, and form handling reduce boilerplate significantly for a CRUD-heavy app.
- **Celery over RQ**: Celery Beat for scheduling, retry policies with exponential backoff, and broader ecosystem support.
- **HTMX over React**: No build step, no separate API layer needed for the dashboard. Server-side rendering with targeted DOM swaps is sufficient for this use case.
- **WhiteNoise for static files**: Eliminates the need for a separate nginx container in development and small deployments.
- **django-celery-beat DB scheduler**: Allows beat schedules to be managed without redeployment.
- **structlog for logging**: JSON structured logs are required for log aggregation pipelines (Loki, Datadog, etc.).

## SRE-Readiness Checklist

- [x] `/healthz/` — liveness probe, no DB hit
- [x] `/readyz/` — readiness probe, checks Postgres + Redis
- [x] `/metrics/` — Prometheus exposition (django-prometheus + custom metrics)
- [x] Structured JSON logs to stdout (structlog)
- [x] All config from environment variables (django-environ, 12-factor)
- [x] `SECRET_KEY` required from env, no fallback
- [x] `DEBUG` defaults to `False`
- [x] Non-root container user (uid 1000)
- [x] Single image, multiple roles (web/worker/beat) via entrypoint
- [x] Multiprocess-safe Prometheus registry (`PROMETHEUS_MULTIPROC_DIR`)
- [x] Database connection pooling (`conn_max_age=60`)
- [x] `CELERY_TASK_ACKS_LATE=True` for graceful shutdown
- [x] `X-Request-ID` propagated on all requests

## Next Steps (Out of Scope)

Infrastructure (Kubernetes, Helm, ArgoCD, GitHub Actions, Prometheus/Grafana/Loki stacks, Terraform, Sealed Secrets, NetworkPolicies, runbooks) is intentionally not included — you will add this layer separately.

For alerting: the `AlertChannel` model is in place as a data model. Wire up actual delivery (email via Django's email backend, or webhook HTTP POST) once the infra layer is ready.
