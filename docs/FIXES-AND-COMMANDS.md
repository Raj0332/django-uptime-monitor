# Project Fixes & Commands — Session Notes

A record of what was reviewed, what was broken, how each issue was fixed, and
every command used. Written so the *why* behind each fix is clear — these
double as interview talking points.

---

## 1. Full project review (Docker → Compose → k8s → Helm)

Goal: verify the whole deployment chain actually works, not just that files exist.

### Commands used

```bash
# Verify the Helm chart is syntactically valid
helm lint helm/uptime-monitor

# Render every template locally (no cluster needed) and count objects
helm template test-release helm/uptime-monitor > rendered.yaml
grep "^kind:" rendered.yaml | sort | uniq -c
```

### Result

- Chart linted clean and rendered **11 objects**: 5 Deployments (web, celery,
  beat, postgres, redis), 3 Services, ConfigMap, Secret, PersistentVolumeClaim.
- Dockerfile: multi-stage build, non-root user — good.
- Liveness (`/healthz/`) and readiness (`/readyz/`) probes point to real Django
  endpoints that have tests.

### Issues found

1. `entrypoint.sh` ran `makemigrations` on every container start (anti-pattern).
2. `DATABASE_URL` (which embeds the DB password) lived in the **ConfigMap**,
   while the same password also lived in the Secret — a credential leak into a
   non-secret object. Present in BOTH the Helm chart and the raw k8s manifests.
3. The Helm ConfigMap was missing `ALLOWED_HOSTS` entirely (the raw k8s
   ConfigMap had it) — a Helm-deployed web pod would answer HTTP 400 to
   everything because Django rejects unknown Host headers.
4. All k8s/Helm work existed only on the `k8s-setup-mac` branch — `main` on
   GitHub (what recruiters see) had none of it.

---

## 2. Fix: migrations generated at runtime (anti-pattern)

### Why it's wrong

- `makemigrations` **generates** schema-change files by diffing models against
  existing migration files. That's a development activity — the output should
  be reviewed and committed to git like any other code.
- Running it at container startup means the schema is generated at runtime:
  different replicas can race, and what runs in production was never reviewed.
- Containers should only **apply** committed migrations: `manage.py migrate`.

### Root cause

`app/monitor/migrations/` contained only `__init__.py` — the migration files
were never committed, which is *why* the entrypoint was forced to generate
them on every start.

### How it was fixed

Step 1 — generate the migration with the project's own image (matches the
pinned Django 5.0.6, not whatever is on the host), mounting the migrations
folder so the generated file lands on the host:

```powershell
docker compose build web

docker compose run --rm --no-deps `
  -v "${PWD}\app\monitor\migrations:/app/monitor/migrations" `
  web python manage.py makemigrations monitor
# -> created app/monitor/migrations/0001_initial.py
#    (models: Site, Check, Incident, AlertChannel)
```

Step 2 — edit `docker/entrypoint.sh`: the `run_migrations()` helper now runs
**only** `python manage.py migrate --noinput` (no makemigrations).

Note: in Kubernetes, migrations are applied ONCE by the migrate Job/Helm hook;
web pods set `RUN_MIGRATIONS_ON_START=false` so multiple replicas don't race
to migrate. In docker-compose the variable is unset (defaults to true), so
web migrates on start as before.

---

## 3. Fix: DB password leaking into the ConfigMap

### Why it's wrong

- `DATABASE_URL=postgres://uptime:PASSWORD@postgres:5432/uptime` embeds a
  credential. ConfigMaps are for non-secret config — they aren't
  access-controlled or encrypted at rest the way Secrets can be.
- Having the password in the Secret AND inside a ConfigMap URL means the
  Secret protection is pointless — anyone who can read ConfigMaps has the
  password.

### How it was fixed

**Helm chart:**

- `templates/configmap.yaml` — removed the `DATABASE_URL` line.
- `templates/secret.yaml` — DATABASE_URL is now assembled inside the Secret
  from values, so the password is written in exactly one place
  (`secrets.postgresPassword`):

```yaml
DATABASE_URL: {{ printf "postgres://%s:%s@postgres:5432/%s"
    .Values.postgres.user .Values.secrets.postgresPassword
    .Values.postgres.database | b64enc | quote }}
```

- `values.yaml` — removed `config.databaseUrl` (no longer needed).
- No deployment changes were needed because web/celery/beat already load env
  from BOTH sources: `envFrom: [configMapRef, secretRef]` — the variable just
  moved from one to the other.

**Raw k8s manifests (same bug, same fix):**

- `k8s/configmap.yaml` — removed `DATABASE_URL`.
- `k8s/secret.yaml` — added it base64-encoded:

```bash
printf '%s' 'postgres://uptime:uptime@postgres:5432/uptime' | base64 -w0
# cG9zdGdyZXM6Ly91cHRpbWU6dXB0aW1lQHBvc3RncmVzOjU0MzIvdXB0aW1l
```

### Verification

```bash
helm template t helm/uptime-monitor > rendered.yaml
```

Then a small Python check against the rendered output — it decodes the
Secret's DATABASE_URL and proves no plaintext credentials leak elsewhere:

```python
import re, base64
s = open("rendered.yaml").read()
m = re.search(r'DATABASE_URL: "([A-Za-z0-9+/=]+)"', s)
print("secret DATABASE_URL decodes to:", base64.b64decode(m.group(1)).decode())
# -> postgres://uptime:uptime@postgres:5432/uptime  (exactly right)

print("ALLOWED_HOSTS present:", "ALLOWED_HOSTS" in s)                     # True
print("plaintext creds outside Secret:",
      "postgres://uptime:uptime" in s.split("kind: Secret")[0])           # False
```

---

## 4. Fix: missing ALLOWED_HOSTS in the Helm chart

`settings.py` defaults `ALLOWED_HOSTS` to `["localhost"]`. The raw k8s
ConfigMap set it, the Helm chart didn't — so Helm deployments would fail Host
header validation (HTTP 400) for anything not called "localhost".

Fix: added to `values.yaml`:

```yaml
config:
  allowedHosts: "localhost,127.0.0.1,web,.svc,.cluster.local"
```

rendered by `templates/configmap.yaml`. When `ingress.enabled=true`, the
ingress host is automatically prepended (and CSRF_TRUSTED_ORIGINS derived).

---

## 5. End-to-end verification (don't trust, observe)

```powershell
docker compose build web        # rebuild with new entrypoint + migration file
docker compose up -d            # start all 5 services

docker compose logs web         # confirms "Applying migrations..." (no makemigrations)

# Hit the real endpoints:
curl http://localhost:8000/healthz/   # {"status": "ok"}
curl http://localhost:8000/readyz/    # {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}

docker compose ps               # all 5 containers Up, db/redis healthy
```

Also removed the obsolete `version: "3.9"` line from `docker-compose.yml`
(Compose v2 ignores it and warns).

---

## 6. Git: the rejected push and the merge conflict

### What happened

```text
! [rejected]  k8s-setup-mac -> k8s-setup-mac (non-fast-forward)
```

Local and remote had **diverged**: local was "ahead 1" (the fixes commit) and
"behind 1" (a commit pushed from the Mac adding ingress, HPA/autoscaling, and
a migrate Job/Helm hook). Git refuses a push that would discard remote
commits — you must integrate them first.

### The fix

```bash
git status -sb        # shows: ahead 1, behind 1  -> diverged
git pull              # merge remote into local -> CONFLICTS in 3 files
```

Conflicts appeared in `docker/entrypoint.sh`,
`helm/uptime-monitor/templates/configmap.yaml`, and
`helm/uptime-monitor/values.yaml`, because both sides edited the same lines.

Resolution principle: the two changesets were **complementary**, so keep both
intents instead of picking a side:

| File | Kept from Mac commit | Kept from fixes |
|---|---|---|
| entrypoint.sh | `RUN_MIGRATIONS_ON_START` gating + `migrate` subcommand | `run_migrations()` runs migrate only (no makemigrations) |
| configmap.yaml | ingress-aware ALLOWED_HOSTS, CSRF origins, RUN_MIGRATIONS_ON_START | DATABASE_URL stays out (lives in Secret) |
| values.yaml | ingress/csrf/runMigrationsOnStart keys | no `databaseUrl` key; in-cluster hostnames kept in allowedHosts |

Compatibility check: the new migrate Job runs `/entrypoint.sh migrate`, which
now applies committed migrations only — consistent with the fix.

### Post-merge verification

```bash
helm lint helm/uptime-monitor                                   # clean
helm template t helm/uptime-monitor                             # 12 objects (11 + migrate Job)
helm template t helm/uptime-monitor \
  --set ingress.enabled=true --set web.autoscaling.enabled=true # 14 objects (+ Ingress, HPA)
```

### Finishing commands (run manually)

```bash
git add -A
git commit -m "merge: combine migrate-only entrypoint and Secret-held DATABASE_URL with ingress/HPA/migrate-hook"
git push

# Publish everything to main — the branch recruiters/visitors see on GitHub:
git checkout main
git pull
git merge k8s-setup-mac
git push origin main
git checkout k8s-setup-mac
```

---

## 7. Supporting / inspection commands used along the way

Small commands used to investigate before fixing — handy to know:

```bash
# Check tools are installed and their versions
helm version --short
kubectl version --client
docker --version

# Start Docker Desktop from a terminal (Windows) when the daemon isn't running
# (error was: "failed to connect to the docker API at npipe:...")
powershell Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
docker info          # works once the engine is actually up

# Confirm probe endpoints really exist in the code (never trust YAML alone)
grep -rn "healthz\|readyz" app/

# See what's inside the migrations package (found only __init__.py -> root cause)
ls app/monitor/migrations/

# List all chart templates
ls helm/uptime-monitor/templates/

# Find which templates reference migrations / env sources
grep -l "migrate" helm/uptime-monitor/templates/*.yaml
grep -rn "envFrom\|secretRef\|configMapRef" helm/uptime-monitor/templates/

# Check how config/secrets render without a cluster, filtered:
helm template t helm/uptime-monitor | grep -A8 "kind: Secret"
helm template t helm/uptime-monitor | grep -A8 "kind: ConfigMap"

# Decode a base64 Secret value to double-check it
echo 'cG9zdGdyZXM6Ly91cHRpbWU6dXB0aW1lQHBvc3RncmVzOjU0MzIvdXB0aW1l' | base64 -d

# Git investigation before the merge
git status -sb                          # "ahead 1, behind 1" = diverged
git log --oneline -5                    # what's on my side
git log origin/k8s-setup-mac -1         # what's on the remote side
git log origin/main..HEAD --oneline     # commits main is missing (why GitHub looked empty)
git branch -a                           # all local + remote branches
```

---

## 8. Interview one-liners from this session

- **Migrations:** "Containers should only apply committed migrations.
  `makemigrations` at startup generates schema at runtime — unreviewed, and
  replicas can race. Migration files belong in code review."
- **Secrets:** "A DB URL with an embedded password *is* a credential. Putting
  it in a ConfigMap defeats the Secret — I assemble DATABASE_URL inside the
  Secret template so the password exists in one place."
- **Probes:** "Liveness says 'restart me if stuck' and must be dependency-free;
  readiness says 'don't route traffic yet' and checks Postgres/Redis. Mixing
  them up causes restart storms when a dependency blips."
- **Diverged branches:** "A non-fast-forward rejection means remote has
  commits I don't. Pull, merge (keeping both intents on conflicts), verify,
  then push — never force-push over a teammate's work."
- **Verification:** "I don't call a fix done until I've watched it work —
  rebuilt the image, brought the stack up, and hit /healthz/ and /readyz/."
