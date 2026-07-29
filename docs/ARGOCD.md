# ArgoCD — GitOps deployment for this project

## What ArgoCD adds (the 30-second explanation)

Without ArgoCD, deploying means running commands *at* the cluster:
`helm upgrade --install ...` from a laptop or CI job. Config drift creeps in,
nobody is sure what's actually deployed, and cluster credentials must be
handed to every deployer.

With ArgoCD, the flow inverts (**pull-based GitOps**):

```
git push  ──▶  GitHub repo (helm/uptime-monitor)
                    ▲
                    │  polls / webhooks
              ┌─────┴─────┐
              │  ArgoCD   │   compares desired state (Git)
              │ (in-cluster)│  vs live state (cluster)
              └─────┬─────┘
                    │  applies the diff
                    ▼
              Kubernetes objects (uptime namespace)
```

- **Git is the single source of truth** — what's deployed is whatever the
  chart at `targetRevision` says. Deploy = merge. Rollback = `git revert`.
- **selfHeal** — if someone `kubectl edit`s a deployment by hand, ArgoCD
  reverts it to match Git within seconds.
- **prune** — delete a manifest from Git and ArgoCD deletes it from the
  cluster. No orphaned objects.

## Install (local: minikube)

```bash
# 1. Start a cluster
minikube start --driver=docker

# 2. Install ArgoCD (its own namespace, official manifests)
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 3. Wait for pods
kubectl -n argocd get pods -w      # until argocd-server is Running (1-3 min)

# 4. Get the initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# 5. Open the UI (leave this running)
kubectl -n argocd port-forward svc/argocd-server 8080:443
# -> https://localhost:8080  (user: admin, password from step 4;
#    accept the self-signed cert warning)
```

## Deploy this app the GitOps way

```bash
kubectl apply -f argocd/application.yaml
```

That's the last manual `kubectl` this project needs. ArgoCD now:
1. clones the repo, renders `helm/uptime-monitor` with `values.yaml`,
2. creates the `uptime` namespace and all objects (web, celery, beat,
   postgres, redis, migrate Job),
3. keeps everything synced to Git forever.

Watch it in the UI: Applications → uptime-monitor → the resource tree shows
every object and its health/sync status.

## The demo loop (use this in interviews)

```bash
# 1. Change something in Git — e.g. bump replicas in helm/uptime-monitor/values.yaml
#      web: { replicas: 2 }
git commit -am "scale web to 2" && git push

# 2. Watch ArgoCD notice (within ~3 min, or click "Refresh") and apply it:
kubectl -n uptime get pods -w        # second web pod appears — no kubectl apply run

# 3. Demonstrate selfHeal — try to drift manually:
kubectl -n uptime scale deploy web --replicas=5
kubectl -n uptime get deploy web -w  # ArgoCD snaps it back to 2 (Git wins)

# 4. Rollback = Git, not kubectl:
git revert HEAD && git push          # cluster returns to 1 replica
```

Being able to run this loop live is stronger interview material than any
resume bullet.

## Useful commands

```bash
# CLI (optional): https://argo-cd.readthedocs.io/en/stable/cli_installation/
argocd app list
argocd app get uptime-monitor
argocd app sync uptime-monitor       # force an immediate sync
argocd app history uptime-monitor    # deploy history
kubectl -n argocd get applications   # Application CRs without the CLI
```

## Interview one-liners

- "GitOps is pull-based: the cluster pulls desired state from Git, instead of
  CI pushing into the cluster. Cluster credentials never leave the cluster."
- "ArgoCD continuously diffs desired state (Git) against live state (cluster)
  and converges them — with selfHeal, manual drift is reverted automatically."
- "Rollback is `git revert` — auditable, reviewable, and identical to any
  other change. That's the point: deployment history IS Git history."
- "At work I operate services deployed via ArgoCD; in my own project I set up
  the full loop myself — Application CR, automated sync with prune and
  selfHeal, Helm chart as the source."
