# Local Kubernetes platform

Runs the task manager on a local Kubernetes cluster: no cloud account
needed. Terraform creates the cluster and its platform (ingress-nginx,
CloudNativePG, Argo CD, Kyverno); **Argo CD deploys the database and the
app from `gitops/` in git** (see the README's GitOps section); `make`
ties it together.

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
make cluster-up      # cluster, platform, Argo CD root app, app SECRET_KEY
make gitops-status   # Argo CD Applications: sync, health, revision
make smoke-test      # GET http://tasks.localhost/healthz/ through the ingress
make status          # pods, services, ingress, jobs, HPA, PDB, database + Argo CD
make argocd-ui       # Argo CD UI on https://localhost:8443 (make argocd-password)
make cluster-down    # delete everything
```

To try work in progress from a branch, point the root Application at it:
`make cluster-up GITOPS_REVISION=feature/my-branch` (and the Applications
in `gitops/apps/`, which CI requires to be back on `main` before merging).

`make build-push dev-deploy` deploys a local, unsigned build into the
`task-manager-dev` namespace, outside GitOps and signature enforcement.

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
| `gitops.tf` | Argo CD, Kyverno, and the root Argo CD Application (app-of-apps); `gitops_auto_sync` pauses its automated sync |
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
  by Argo CD from the `task-manager-db` chart.
- **Argo CD** (chart 10.11.6): Dex, notifications and the ApplicationSet
  controller are off; one replica each, with memory limits that fit a
  ~4 GB Docker VM (controller 512 Mi, repo-server 256 Mi, server 192 Mi,
  Redis 96 Mi). Reconciles every 60 s. The UI has **no ingress**: use
  `make argocd-ui` (port-forward). The admin password is random
  (`random_password`, stored as a bcrypt hash in Argo CD and in the local
  Terraform state; `make argocd-password`), so `argocd-initial-admin-secret`
  is never needed, and Terraform deletes it if present.
- **Kyverno** (chart 3.9.2): admission controller only (background,
  cleanup and reports controllers off), ~128 Mi. Enforces the image
  signature policies in `gitops/platform/policies.yaml`.
- **Root Application** (`argocd-apps` chart): syncs `gitops/apps/` from
  `var.gitops_revision` (default `main`).

### Why Kyverno, not Sigstore policy-controller

Both were tested against the real images before choosing:

| | policy-controller 0.13.1 | Kyverno `ClusterPolicy` | Kyverno `ImageValidatingPolicy` |
|---|---|---|---|
| Our image (cosign 3 bundle, OCI referrer) | ❌ "no signatures found" | ✅ | ✅ |
| CloudNativePG images (cosign 3 bundle) | ❌ "no signatures found" | ❌ "no matching signatures" | ✅ |
| Wrong signer / unsigned digest | — | — | ✅ denied |

cosign 3 stores signatures as Sigstore bundles attached via OCI referrers.
policy-controller 0.13 only reads the older `.sig`-tag format, so it can't
see them; signing our image in the old format too wouldn't have helped,
because the CloudNativePG images would still fail and need an exemption.
Kyverno's newer `ImageValidatingPolicy` API verifies all of them, so the
policies use only that (plus a `ValidatingPolicy` for default deny).

### Moving existing Helm releases under Argo CD

The cluster from Stage 1 had the app and database installed with
`helm install`. They were handed to Argo CD **without recreating
anything** (so the database kept its data): Helm's release records
(`sh.helm.release.v1.*` Secrets) were deleted, and Argo CD adopted the
existing resources, which have the same names. On a fresh cluster there's
nothing to adopt.

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

## Protecting stateful resources

The database must never be deleted as a side effect of a GitOps
operation. Three layers make sure of that:

| What | Protection |
|---|---|
| CNPG `Cluster` (`deploy/helm/task-manager-db`) | `argocd.argoproj.io/sync-options: Delete=false,Prune=false`: Argo CD never deletes it, even if it's removed from git or its Application is deleted |
| `task-manager` Namespace (`gitops/platform`) | the same annotation: deleting the namespace would delete the database with it |
| `task-manager-db` Application | **no** `resources-finalizer`: deleting the Application doesn't cascade to the resources it manages |

The `platform` and `task-manager` Applications keep the finalizer: their
resources are stateless and safe to recreate.

**Tested on the cluster:** `kubectl delete application task-manager-db`
left the Cluster, its PVC and the Postgres pod untouched (the same object
IDs before and after), and user `k8s-demo` could still log in throughout.
The root Application recreated `task-manager-db` within about 4 seconds; it
adopted the existing Cluster (same UID) and went back to Synced/Healthy.

Deleting the database is therefore always a deliberate, manual step:

```bash
kubectl --context k3d-tasks -n task-manager delete cluster.postgresql.cnpg.io task-manager-db
```

## Kyverno outage runbook

Kyverno enforces image signatures in `task-manager`
(`gitops/platform/policies.yaml`). Whether an outage **blocks** or
**allows** new pods depends on how Kyverno went down; both were tested:

| Kyverno is... | Its webhooks | New pods in `task-manager` | Running pods |
|---|---|---|---|
| running | registered, `failurePolicy: Fail` | only signed images | unaffected |
| crashed / unreachable (no endpoints, network) | still registered | **all refused** (fail-closed), even signed ones | unaffected |
| shut down gracefully (scaled to 0, uninstalled) | **deleted by Kyverno on shutdown** | **backstop only**: images from the 3 allowed repositories, ours pinned by digest; **signatures not checked** | unaffected |

The third row is Kyverno's own design: it removes its webhooks on a clean
shutdown so a stopped Kyverno can't block the whole cluster. The
[backstop](../gitops/platform/backstop.yaml) is a native
`ValidatingAdmissionPolicy` evaluated by the API server itself, so it
always applies. During a graceful outage it still rejects other
registries and tag-only images, but **an unsigned digest from our own
repository would be admitted** (tested). Treat a stopped Kyverno as a
security incident, not just an availability problem.

**While Kyverno is refusing pods (fail-closed),** nothing new starts in
`task-manager`: Argo CD syncs fail at the migration hook, the HPA can't
scale up, and pods evicted by a node drain can't be rescheduled. Running
pods keep serving.

**Diagnose:**

```bash
kubectl --context k3d-tasks -n kyverno get pods
kubectl --context k3d-tasks -n kyverno logs deploy/kyverno-admission-controller --tail=50
kubectl --context k3d-tasks get validatingwebhookconfigurations | grep kyverno
kubectl --context k3d-tasks -n task-manager get events --field-selector reason=FailedCreate
#   "failed calling webhook ..."  -> Kyverno unreachable (fail-closed)
#   "... not signed by the expected identity" -> Kyverno working; the image is the problem
```

**Recover:**

1. Restart Kyverno, or reapply its declared state (Terraform resets the
   replica count and settings):

   ```bash
   kubectl --context k3d-tasks -n kyverno rollout restart deploy/kyverno-admission-controller
   terraform -chdir=infra/terraform apply
   ```

   Kyverno re-registers its webhooks when it starts. Argo CD then retries
   any failed sync on its own.
2. If Kyverno was **gracefully** stopped, check what started without
   signature verification during the gap. List pods newer than the outage
   and verify each image digest:

   ```bash
   kubectl --context k3d-tasks -n task-manager get pods \
     -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp,IMAGE:.spec.containers[0].image
   cosign verify <image@sha256:...> \
     --certificate-identity https://github.com/Shayur-p60/django-task-manager/.github/workflows/ci.yml@refs/heads/main \
     --certificate-oidc-issuer https://token.actions.githubusercontent.com
   ```

   Delete any pod whose image fails verification; its controller
   recreates it, and Kyverno now checks the replacement.

**Break-glass** (only if Kyverno can't be recovered and pods *must*
start): delete Kyverno's validating webhook configurations. Signature
checks stop; the backstop still restricts registries and requires
digests. Kyverno recreates its webhooks as soon as it runs again.

```bash
kubectl --context k3d-tasks get validatingwebhookconfigurations -o name | grep kyverno \
  | xargs kubectl --context k3d-tasks delete
```

Don't remove the namespace's `images.task-manager/verify` label instead:
Argo CD puts it back within a minute, and it also turns off the backstop.

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
- **Self-heal fails with `Service ... spec.ports[1].name: Duplicate
  value`:** someone changed a Service *port number* by hand. Ports are
  merged by port number, so Argo CD's "set it back to 80" is read as "add
  a second port 80", and both are named `http`. Fix the port by hand
  (`kubectl ... patch svc ...`); Argo CD's next sync succeeds. Other
  manual changes (env vars, labels, deleted resources) self-heal on
  their own.
- **A sync keeps retrying an old commit:** after a bad commit is reverted,
  Argo CD finishes (or retries) the operation in progress first. Stop it
  with `argocd app terminate-op task-manager`, or
  `kubectl --context k3d-tasks -n argocd patch application task-manager
  --type merge -p '{"status":{"operationState":{"phase":"Terminating"}}}'`.
- **Pods or the migration Job denied by Kyverno:** the image isn't signed
  by the expected workflow (see `gitops/platform/policies.yaml`). Check
  with `kubectl --context k3d-tasks -n task-manager get events
  --field-selector reason=FailedCreate`. On a cold cache, verification can
  take several seconds; the policies allow 30 s.
- **Migration Job fails on a fresh cluster:** the `SECRET_KEY` Secret is
  created by `make secrets` (part of `cluster-up`). Argo CD retries the sync,
  so it recovers once the Secret exists.
- **Pods not ready:** `make status` and `make logs`. Readiness fails
  while the database is unavailable; liveness doesn't, so pods aren't
  restarted for it.
- **ingress-nginx support:** the upstream ingress-nginx project has
  ended active maintenance. It's fine for a local platform; for
  long-term use consider moving to the Gateway API (e.g. Envoy Gateway
  or Traefik).
