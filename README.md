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

## Kubernetes Deployment (Phase 2)

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| Docker Desktop | Container runtime | [docker.com](https://docker.com) |
| minikube | Local Kubernetes cluster | `winget install Kubernetes.minikube` |
| kubectl | K8s CLI | `winget install Kubernetes.kubectl` |

### K8s Manifests

```
k8s/
├── namespace.yaml          Isolated environment (namespace: uptime)
├── configmap.yaml          Non-sensitive env vars (DATABASE_URL, REDIS_URL)
├── secret.yaml             Sensitive values (SECRET_KEY, POSTGRES_PASSWORD) base64 encoded
├── postgres.yaml           PostgreSQL deployment + PersistentVolumeClaim + Service
├── redis.yaml              Redis deployment + Service
├── deployment-web.yaml     Django app deployment with liveness/readiness probes
├── deployment-celery.yaml  Celery worker deployment
├── deployment-beat.yaml    Celery beat scheduler deployment
└── service-web.yaml        NodePort service to expose web app externally
```

### Start minikube

```powershell
minikube start --driver=docker --memory=2048 --cpus=2
kubectl get nodes
# Expected: minikube   Ready   control-plane
```

### Build and push Docker image

```powershell
# Login to Docker Hub
docker login

# Build for linux/amd64 (required for minikube on Windows)
docker buildx build --platform linux/amd64 -t rajkumar332/uptime-monitor:latest --push -f docker/Dockerfile .
```

### Apply manifests (order matters)

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/service-web.yaml
kubectl apply -f k8s/deployment-web.yaml
kubectl apply -f k8s/deployment-celery.yaml
kubectl apply -f k8s/deployment-beat.yaml
```

### Verify all pods are running

```powershell
kubectl get pods -n uptime
# Expected output:
# NAME              READY   STATUS    RESTARTS
# postgres-xxx      1/1     Running   0
# redis-xxx         1/1     Running   0
# web-xxx           1/1     Running   0
# celery-xxx        1/1     Running   0
# beat-xxx          1/1     Running   0
```

### Open the app

```powershell
minikube service web -n uptime
```

### Create superuser

```powershell
kubectl exec -it deployment/web -n uptime -- python manage.py createsuperuser
```

### Useful kubectl commands

```powershell
# Check pod logs
kubectl logs -n uptime deployment/web
kubectl logs -n uptime deployment/celery
kubectl logs -n uptime deployment/beat

# Restart a deployment
kubectl rollout restart deployment/web -n uptime

# Check all resources
kubectl get all -n uptime

# Describe a pod (shows events and errors)
kubectl describe pod -n uptime

# Delete everything and start fresh
kubectl delete namespace uptime
```

### Issues faced and fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `exec format error` | Image built on Mac ARM, ran on Windows AMD64 | Rebuild with `--platform linux/amd64` |
| `could not translate host name 'db'` | docker-compose uses `db`, K8s service named `postgres` | Added `DATABASE_URL` with `postgres` host in configmap |
| `configmap uptime-config not found` | ConfigMap missing `namespace: uptime` | Added `namespace: uptime` to configmap metadata |
| `site can't be reached` | Service type was `ClusterIP` | Changed to `NodePort` for external access |
| `CrashLoopBackOff` | Web pod started before postgres/redis were ready | Applied postgres and redis manifests first |

## Next Steps (Out of Scope)

Infrastructure (Kubernetes, Helm, ArgoCD, GitHub Actions, Prometheus/Grafana/Loki stacks, Terraform, Sealed Secrets, NetworkPolicies, runbooks) is intentionally not included — you will add this layer separately.

For alerting: the `AlertChannel` model is in place as a data model. Wire up actual delivery (email via Django's email backend, or webhook HTTP POST) once the infra layer is ready.

## Environment Setup

Create a `.env` file in the project root before running:

```bash
cat > .env << 'EOF'
SECRET_KEY=please-generate-a-secure-key-using-django-secret-key-generator
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://uptime:uptime@db:5432/uptime
REDIS_URL=redis://redis:6379/0
POSTGRES_USER=uptime
POSTGRES_PASSWORD=uptime
POSTGRES_DB=uptime
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
EOF
```

> Generate a secure `SECRET_KEY` with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
