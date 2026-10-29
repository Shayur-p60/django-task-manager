# Local Kubernetes platform

Runs the task manager on a local Kubernetes cluster: no cloud account
needed. Terraform creates the cluster and its add-ons; Helm deploys the
database and the app; `make` ties it together.

```
                 your Mac
  http://tasks.localhost ──► 127.0.0.1:80
                                 │
  ┌──────────── k3d cluster "tasks" (k3s in Docker) ─────────────────┐
  │  k3d load balancer ─► ingress-nginx ─► Service task-manager       │
  │                                          │                        │
  │                          web pods (gunicorn, 2–4, HPA)            │
  │                                          │ DATABASE_URL           │
  │                          CloudNativePG cluster task-manager-db    │
  │  1 server + 2 agent nodes                                         │
  └───────────────────────────────────────────────────────────────────┘
  local registry k3d-tasks-registry.localhost:5111 ◄── make build-push
```

## Prerequisites

Docker Desktop (running) and these tools:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform k3d helm kubeconform
```

`kubectl` is also needed (`brew install kubectl`). Terraform comes from
HashiCorp's tap because the Homebrew core formula is no longer updated.

## Quick start

From the repository root:

```bash
make cluster-up      # cluster, registry, ingress-nginx, CloudNativePG
make build-push      # build the image, push it tagged with the git SHA
make deploy          # database release, then the app release
make smoke-test      # GET http://tasks.localhost/healthz/ through the ingress
make status          # pods, services, ingress, jobs, HPA, PDB, database
make cluster-down    # delete everything
```

`make help` lists all targets. `make lint` runs the same Terraform and
Helm checks as CI.

`tasks.localhost` resolves to `127.0.0.1` on macOS without editing
`/etc/hosts`; the Makefile's `curl` calls also pin it explicitly.

## What Terraform creates (`infra/terraform/`)

| File | Contents |
|---|---|
| `versions.tf` | Terraform and provider versions, and the backend |
| `variables.tf` | Cluster name, node count, ports, chart versions |
| `main.tf` | The k3d cluster + registry, and Helm releases for ingress-nginx and CloudNativePG |
| `providers.tf` | Helm provider, pinned to the k3d context |
| `outputs.tf` | Kube context, registry addresses, app URL |
| `templates/k3d-config.yaml.tftpl` | k3d cluster config, filled from the variables |

- **Cluster:** 1 server, 2 agents. Traefik (bundled with k3s) is
  disabled because ingress-nginx is used instead.
- **Ports:** the cluster's load balancer listens on `127.0.0.1:80` and
  `127.0.0.1:443` only, not on your network.
- **Registry:** `k3d-tasks-registry.localhost`, published on
  `localhost:5111` (5000 is used by macOS AirPlay). Push to
  `localhost:5111/...`; the cluster pulls the same image as
  `k3d-tasks-registry.localhost:5111/...`.
- **ingress-nginx:** exposed through k3s's built-in service load
  balancer. `use-forwarded-headers` is off, so the controller overwrites
  `X-Forwarded-*` headers from clients; the app trusts
  `X-Forwarded-Proto` and counts one proxy (`NUM_PROXIES=1`).
- **CloudNativePG:** the operator only. The database itself is deployed
  by the `task-manager-db` Helm chart.

### Why the cluster is created with the k3d CLI, not a Terraform provider

There is no official k3d provider. The community ones are maintained by
individuals, lag behind k3d releases, and have broken on k3d config
changes before. The k3d CLI is the supported interface, so Terraform:

1. renders a k3d config file from the variables (`local_file`),
2. runs `k3d cluster create --config ...` from a `terraform_data`
   resource, and `k3d cluster delete` on destroy,
3. recreates the cluster when the rendered config changes.

The cluster's shape still lives in Terraform variables, it's still
created and destroyed by `terraform apply` / `destroy`, and the Helm
releases depend on it. What's lost compared with a real provider:
Terraform doesn't read the cluster's live state, so a cluster deleted
outside Terraform (`k3d cluster delete`) isn't noticed until the next
apply fails. Run `terraform apply -replace=terraform_data.cluster` to
recreate it in that case.

### Your kubectl context is never switched

k3d normally makes a new cluster your current kubectl context. Here
that's turned off (`switchCurrentContext: false` in the k3d config):
k3d only *adds* a `k3d-tasks` context to `~/.kube/config`.

This protects any other clusters in your kubeconfig (for example a
cloud cluster that's currently selected). Nothing in this setup relies
on the current context:

- the Terraform Helm provider sets `config_context = "k3d-tasks"`,
- every Makefile `kubectl`/`helm` call passes `--context` /
  `--kube-context k3d-tasks`,
- `deploy`, `smoke-test`, `status`, `logs` and `undeploy` first run
  `make kube-context-check`, which fails if the `k3d-tasks` context is
  missing or the cluster doesn't answer.

When running commands by hand, pass the context too:

```bash
kubectl --context k3d-tasks -n task-manager get pods
```

### State and moving to a remote backend

State is stored locally in `infra/terraform/terraform.tfstate`
(git-ignored). The provider lock file, `.terraform.lock.hcl`, is
committed so everyone gets the same provider builds.

To share state later, replace the `backend "local"` block in
`versions.tf` with a remote backend, for example:

```hcl
backend "s3" {
  bucket = "my-tf-state"
  key    = "task-manager/local-platform.tfstate"
  region = "eu-west-1"
}
```

then run `terraform -chdir=infra/terraform init -migrate-state`. No other
file needs to change: everything else reads variables and outputs.

## Helm charts (`deploy/helm/`)

Two releases, installed in this order by `make deploy`:

1. **`task-manager-db`**: a CloudNativePG `Cluster` (1 instance, 1 Gi).
   CNPG creates the Secret `task-manager-db-app`, whose `uri` key is the
   app's `DATABASE_URL`.
2. **`task-manager`**: the app.

They're separate because the app's migration Job is a Helm
`pre-install` / `pre-upgrade` hook. Hooks run *before* the release's
normal resources are created, so on a first install the database and
its Secret must already exist. Making the database a hook as well would
take it out of Helm's normal lifecycle, and an upgrade could delete and
recreate it.

### The app chart

- **Deployment:** gunicorn, `RUN_MIGRATIONS=0`.
  - Liveness probe on `/livez/` (process only), readiness on `/healthz/`
    (app + database), plus a startup probe. Probes send
    `Host: tasks.localhost` so Django's `ALLOWED_HOSTS` accepts them.
  - Requests and limits on CPU and memory.
  - Runs as uid 10001 (non-root) with a read-only root filesystem (only
    `/tmp` is writable), all capabilities dropped, no privilege
    escalation, and the `RuntimeDefault` seccomp profile. No service
    account token is mounted.
  - With the HPA enabled the Deployment has no `replicas` field, so
    `helm upgrade` doesn't reset the replica count the HPA chose.
- **Migration Job:** a `pre-install,pre-upgrade` hook. It's deleted
  before the next run and after success; a **failed Job is kept** so you
  can read its logs
  (`kubectl --context k3d-tasks -n task-manager logs job/task-manager-migrate`).
  `backoffLimit: 2`, `activeDeadlineSeconds: 300`.
- **Secrets:** `SECRET_KEY` comes from the Secret
  `task-manager-secret-key`, which `make deploy` creates once with a
  random value. It's never in `values.yaml`. This is a placeholder until
  proper secrets management is added.
- **Ingress:** `tasks.localhost` via the `nginx` IngressClass.
  `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are derived from the same
  `host` value.
- **HPA:** 2–4 replicas at 70% CPU (k3s ships metrics-server).
- **PodDisruptionBudget:** at least 1 pod stays available during node
  drains.
- **Image:** `image.tag` is required; the chart refuses to render with
  an empty tag or `latest`. `make build-push` / `make deploy` use the git
  SHA, with `-dirty` added when there are uncommitted changes.

## Troubleshooting

- **Port 80 or 443 in use:** `terraform -chdir=infra/terraform apply
  -var http_port=8080 -var https_port=8443`, then use
  `make ... HTTP_PORT=8080`. Changing ports recreates the cluster.
- **Migration Job failed:** its pod is kept; read
  `kubectl --context k3d-tasks -n task-manager logs job/task-manager-migrate`.
  The next `make deploy` replaces it.
- **`helm upgrade` fails with "conflict occurred while applying object":**
  Helm 4 uses server-side apply, so it won't overwrite a field someone
  changed by hand (e.g. `kubectl patch hpa ...`). Remove the manual
  change from the cluster, or run the upgrade once with
  `--force-conflicts` to hand the field back to Helm. Make changes
  through `values.yaml` instead of `kubectl edit`/`patch`.
- **Pods not ready:** `make status` and `make logs`. Readiness fails
  while the database is unavailable; liveness doesn't, so pods aren't
  restarted for it.
- **ingress-nginx support:** the upstream ingress-nginx project has
  ended active maintenance. It's fine for a local platform; for
  long-term use consider moving to the Gateway API (e.g. Envoy Gateway
  or Traefik).
