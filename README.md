# Task Manager — Django Web App with Authentication

A task manager built with Django covering the full authentication
lifecycle: registration, login (with brute-force throttling), logout,
password reset via email, and role-based permissions. It also has a
token-authenticated REST API (Django REST Framework) with OpenAPI docs.

## Features

- **Registration, login, logout** — Django's built-in auth system.
  Passwords are hashed with PBKDF2 (`UserCreationForm` handles this
  automatically — nothing is ever stored in plaintext).
- **Login throttling** — after 5 failed login attempts for a given
  username, further attempts are blocked for 15 minutes, even if the
  correct password is eventually entered. See `tasks/forms.py`
  (`ThrottledAuthenticationForm`).
- **Role-based permissions** — regular users see and manage only their
  own tasks (`/dashboard/`). Staff users additionally get
  `/admin-dashboard/`, showing every user's tasks. A logged-in
  non-staff user hitting the admin view gets a proper `403 Forbidden`
  (not a confusing "please log in" redirect — they *are* logged in,
  they just lack permission).
- **Tasks** — each task has a title, description, due date, priority
  (low/medium/high) and done flag. The dashboard filters by status and
  priority, searches titles, sorts by due date or priority, pages 10 at
  a time, and highlights overdue tasks.
- **REST API** — full CRUD at `/api/tasks/` with token or session auth,
  filtering, search, ordering and pagination. Interactive docs at
  `/api/docs/`. See [REST API](#rest-api) below.
- **Password reset via email** — the full built-in flow (request →
  emailed link → set new password → confirmation).
- **Secrets kept out of source control** — `SECRET_KEY`, `DEBUG`,
  `ALLOWED_HOSTS`, the database and email settings are read from
  environment variables via `python-decouple`, not hardcoded in
  `settings.py`.
- **Production-ready** — PostgreSQL through `DATABASE_URL`, gunicorn,
  static files served by whitenoise, HTTPS-only cookies and HSTS when
  `DEBUG=False`, a `/healthz/` endpoint, and a Docker image that runs as
  a non-root user. See [Run with Docker](#run-with-docker) and
  [Deploying](#deploying-to-render-or-railway).

## Setup

```bash
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # keeps DEBUG=True for local development

python manage.py migrate
python manage.py createsuperuser   # creates a staff/admin account
python manage.py runserver
```

Then visit `http://127.0.0.1:8000/register/` to create a regular
account, or log in with the superuser you created to see the admin
dashboard at `/admin-dashboard/`.

Requires Python 3.12 or newer (Django 6.1). Without `DATABASE_URL`
the app uses a local SQLite file, `db.sqlite3`.

`DEBUG` defaults to `False`, so without a `.env` the app runs with the
production settings: it redirects to HTTPS and refuses to start with the
built-in `SECRET_KEY`. Copy `.env.example` as above for local work.

### Trying the password reset flow locally

1. Go to `/password-reset/` and enter an existing account's email.
2. Check the terminal running `runserver` — the "email" prints there
   instead of actually being sent (Django's default console mailer).
3. Copy the reset link into your browser to set a new password.

## Run with Docker

`docker-compose.yml` runs the production setup locally: the app under
gunicorn plus PostgreSQL. Migrations run automatically when the web
container starts.

```bash
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
docker compose up --build
```

Open `http://localhost:8000`. To create an admin account:

```bash
docker compose exec web python manage.py createsuperuser
```

Password reset emails are printed in the `docker compose` output. Stop
with `Ctrl+C`; `docker compose down -v` also deletes the database.

`docker compose ps` shows both services as `healthy` once the database
accepts connections and `/healthz/` answers. Compose sets
`USE_HTTPS=False` because it serves plain HTTP on localhost; a real
deployment must leave that out.

To build and run only the image:

```bash
docker build -t task-manager .
docker run --rm -p 8000:8000 \
  -e SECRET_KEY="$SECRET_KEY" -e ALLOWED_HOSTS=localhost -e USE_HTTPS=False \
  -e ALLOW_CONSOLE_EMAIL=True \
  task-manager
```

Without `DATABASE_URL` this uses SQLite inside the container, so data is
lost when the container stops.

### How the image works

- Based on `python:3.12-slim` and runs as a non-root user (`appuser`).
- Static files are collected at build time and served by whitenoise.
- `docker-entrypoint.sh` first runs
  `python manage.py check --deploy --fail-level ERROR`, then `migrate`,
  then starts gunicorn. The check always runs, even with
  `RUN_MIGRATIONS=0`, so the container stops immediately if
  `SECRET_KEY` is missing or the built-in default, or if email isn't
  configured (see `ALLOW_CONSOLE_EMAIL` below). Set `RUN_MIGRATIONS=0`
  to skip migrations.
- gunicorn listens on `$PORT` (default `8000`) with `$WEB_CONCURRENCY`
  workers (default `2`). See `gunicorn.conf.py`.

## Configuration

All settings come from environment variables (or `.env` locally). See
`.env.example` for the full list.

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | insecure dev key | **Required** when `DEBUG=False`; the app won't start without it |
| `DEBUG` | `False` | `True` only for local development |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names |
| `DATABASE_URL` | SQLite file | e.g. `postgres://user:pass@host:5432/db` |
| `CSRF_TRUSTED_ORIGINS` | empty | e.g. `https://tasks.example.com`, only if needed |
| `USE_HTTPS` | `True` | `False` only for plain-HTTP local testing |
| `SECURE_HSTS_SECONDS` | `2592000` (30 days) | Raise once HTTPS is known to work |
| `EMAIL_BACKEND` | console | `django.core.mail.backends.smtp.EmailBackend` to send real email |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | | SMTP details |
| `DEFAULT_FROM_EMAIL` | `Task Manager <noreply@localhost>` | Sender for password reset emails |
| `ALLOW_CONSOLE_EMAIL` | `False` | `True` lets the Docker image start with the console email backend (emails only go to the logs) |
| `NUM_PROXIES` | unset | Number of proxies in front of the app, for the API's per-IP throttle; usually `1` on Render/Railway |
| `PORT`, `WEB_CONCURRENCY` | `8000`, `2` | gunicorn |
| `RUN_MIGRATIONS` | `1` | `0` skips `migrate` at container start |

With `DEBUG=False` the app redirects HTTP to HTTPS, marks session and
CSRF cookies `Secure`, sends HSTS, and trusts the `X-Forwarded-Proto`
header from the hosting platform's proxy. `/healthz/` is exempt from
the HTTPS redirect so platform health checks work.

To check the production settings:

```bash
DEBUG=False ALLOWED_HOSTS=tasks.example.com \
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend EMAIL_HOST=smtp.example.com \
python manage.py check --deploy
```

`check --deploy` reports an error for the console email backend,
because password reset emails would never be sent. Configure SMTP for a
real deployment, or set `ALLOW_CONSOLE_EMAIL=True` to accept emails only
appearing in the logs (docker compose does this). The Docker image runs
this check on every start, so it won't start until one of the two is
done. The HSTS preload warning (`security.W021`) is silenced because
preload is opt-in through `SECURE_HSTS_PRELOAD`.

### Security notes

- **Only expose the app through a proxy that sets `X-Forwarded-Proto`.**
  With `DEBUG=False`, Django's `SECURE_PROXY_SSL_HEADER` treats any
  request carrying `X-Forwarded-Proto: https` as secure. That's correct
  behind Render's or Railway's proxy, which set or overwrite the header
  on every request. If clients can reach gunicorn directly (for example
  a published port on a public server), they can send that header
  themselves, so plain-HTTP requests would be treated as HTTPS: no
  redirect, and `Secure` cookies sent over HTTP. Keep port 8000 private,
  or put a proxy in front that overwrites the header.
- **API tokens don't expire.** A token from `/api/token/` stays valid
  until it's deleted. Treat it like a password. To revoke one, delete it
  under *Auth Token → Tokens* in the Django admin (or delete the user);
  the next `POST /api/token/` then issues a new one.
- **Set `NUM_PROXIES` behind a proxy.** The per-IP limit on
  `/api/token/` identifies clients by IP address. Behind a proxy, every
  request arrives from the proxy's IP, so all clients would share one
  limit. Set `NUM_PROXIES` to the number of proxies in front of the app
  (usually `1` on Render or Railway; check your platform's docs) so DRF
  reads the real client IP from `X-Forwarded-For`. Don't set it when
  clients connect directly: then `X-Forwarded-For` comes from the
  client and could be faked to dodge the limit. The per-username
  lockout doesn't depend on IPs and works either way.

## Deploying to Render or Railway

Both platforms build the `Dockerfile` directly, provide PostgreSQL, end
HTTPS at their proxy, and set `$PORT`, which gunicorn already uses.

### Render

1. Create a **PostgreSQL** database. Copy its *Internal Database URL*.
2. Create a **Web Service** from this repository. Render detects the
   Dockerfile.
3. Set these environment variables:
   - `SECRET_KEY`: a long random string (or use *Generate*)
   - `DATABASE_URL`: the internal URL from step 1
   - `ALLOWED_HOSTS`: `your-app.onrender.com` (plus any custom domain)
   - `NUM_PROXIES`: `1`
   - Email: `DEFAULT_FROM_EMAIL` and the `EMAIL_*` SMTP variables. Without
     them, set `ALLOW_CONSOLE_EMAIL=True` or the container won't start
     (password reset emails then only appear in the logs)
4. Set the **Health Check Path** to `/healthz/`.
5. Deploy. Migrations run when the container starts.
6. Create an admin from the service's **Shell** tab:
   `python manage.py createsuperuser`.

### Railway

1. Create a project, add **PostgreSQL**, then add a service from this
   GitHub repository. Railway builds the Dockerfile.
2. In the service's **Variables**, set:
   - `SECRET_KEY`: a long random string
   - `DATABASE_URL`: `${{Postgres.DATABASE_URL}}` (a reference to the
     database service)
   - `ALLOWED_HOSTS`: your generated domain, e.g.
     `your-app.up.railway.app`
   - `NUM_PROXIES`: `1`
   - email variables as for Render (SMTP, or `ALLOW_CONSOLE_EMAIL=True`)
3. Under **Settings → Networking**, generate a domain. Optionally set
   the health check path to `/healthz/`.
4. Create an admin with the Railway CLI:
   `railway run python manage.py createsuperuser`, or from the
   service's shell.

### Notes for both

- Running more than one instance? Set `RUN_MIGRATIONS=0` on the web
  service and run `python manage.py migrate` as a pre-deploy or release
  command, so instances don't migrate at the same time.
- The login throttle counters use Django's in-memory cache, so they
  are per instance. With several instances, configure a shared cache
  such as Redis.
- `SECURE_HSTS_SECONDS` starts at 30 days. Browsers remember it, so
  only raise it (for example to a year) once HTTPS works on every
  domain you use.

## Secure CI/CD pipeline

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every pull
request, every push to `main`, and weekly. Security gates fail the build
on real findings and upload their results (SARIF) to the repository's
**Security → Code scanning** tab. Only a push to `main` publishes an
image, and only after every gate has passed.

```mermaid
flowchart LR
    trigger(["PR / push to main / weekly"]) --> tests & gates

    subgraph tests["Tests"]
        direction TB
        pytest["pytest +<br/>check --deploy"] --> smoke["Docker smoke test<br/>(compose + insecure-key refusal)"]
        k8s["Terraform fmt/validate<br/>helm lint + kubeconform"]
    end

    subgraph gates["Security gates (SARIF → Security tab)"]
        direction TB
        secrets["gitleaks<br/>full history"]
        sast["Semgrep<br/>Python + Django"]
        deps["pip-audit<br/>requirements*.txt"]
        iac["Trivy config<br/>Terraform · Helm · Dockerfile"]
        lint["hadolint<br/>Dockerfile"]
        scan["Trivy image amd64 + arm64<br/>(PRs + weekly)"]
    end

    tests & gates --> gate{"push to main?"}
    gate -- no --> done(["done"])
    gate -- yes --> publish

    subgraph publish["publish (main only)"]
        direction TB
        subgraph perarch["per platform, native runners"]
            direction LR
            amd["amd64: build once →<br/>Trivy scan → push"]
            arm["arm64: build once →<br/>Trivy scan → push"]
        end
        perarch --> index["multi-arch index<br/>from the 2 scanned digests<br/>tag = git SHA"]
        index --> sbom["Syft SBOM per platform<br/>→ cosign attest"]
        sbom --> sign["cosign sign --recursive<br/>index + platforms<br/>(keyless OIDC)"]
        sign --> verify["cosign verify +<br/>verify-attestation"]
    end
```

| Stage | Tool | Fails on |
|---|---|---|
| Secrets | gitleaks (full git history) | any finding |
| Code | Semgrep (`p/python`, `p/django`) | `ERROR` severity |
| Dependencies | pip-audit | any vulnerability in `requirements.txt`; `requirements-dev.txt` only warns |
| Infrastructure | Trivy config: `infra/terraform`, rendered Helm charts, `Dockerfile` | HIGH / CRITICAL |
| Dockerfile | hadolint | warnings and errors |
| Image | Trivy (OS + Python packages), amd64 and arm64 | HIGH / CRITICAL with a fix available |

**Publishing** (push to `main` in this repository only), for
**linux/amd64 and linux/arm64** so the image runs natively on Apple
Silicon as well as x86 servers:

1. **Per platform, on a native runner** (`ubuntu-24.04` and
   `ubuntu-24.04-arm`, no emulation): **build once** with Docker Buildx,
   **scan** that exact image with Trivy, check the image ID hasn't
   changed, and **push** it as `:<sha>-amd64` / `:<sha>-arm64` using
   `GITHUB_TOKEN` (`packages: write`). The digest the push returned is
   handed to the next job.
2. **Index**: `docker buildx imagetools create` makes the multi-arch
   image `ghcr.io/shayur-p60/task-manager:<sha>` from exactly those two
   digests. Digests are content hashes, so the index can only point at
   what was scanned; the job also checks it lists those two and nothing
   else.
3. **SBOM**: Syft generates SPDX JSON for each platform from its pushed
   digest; cosign attaches each as a signed attestation (also uploaded
   as artifacts).
4. **Sign** the index with cosign keyless signing (GitHub OIDC,
   `id-token: write` on this job only); `--recursive` signs both
   platform images too, so a platform-specific pull verifies as well.
5. **Verify** the index and platform signatures and both SBOM
   attestations in the same run, pinned to this repository's workflow
   on `main`.

Pull requests build and scan **both** platforms too (the
`Image scan (Trivy)` check covers both), so an arm64-only build or
vulnerability problem is caught before merge.

To verify an image yourself, see [SECURITY.md](SECURITY.md#verify-an-image-yourself).

**Hardening of the pipeline itself:**
- All actions are pinned to full commit SHAs, and downloaded tools are
  pinned by SHA-256.
- The workflow token is read-only by default; jobs request extra
  permissions individually.
- `pull_request_target` is never used.
- The base image is pinned by digest.
- Dependabot keeps pip packages, the base image and the actions up to
  date.

Details, accepted findings and the manual repository settings are in
[SECURITY.md](SECURITY.md).

### Running the scanners locally

```bash
brew install gitleaks trivy hadolint syft cosign
pip install semgrep pip-audit

gitleaks git . --config .gitleaks.toml --redact
semgrep scan --config p/python --config p/django --metrics off
pip-audit -r requirements.txt
hadolint Dockerfile
trivy config infra/terraform
docker build -t task-manager:scan . && .github/scripts/scan-image.sh task-manager:scan
```

## Run on local Kubernetes (GitOps)

The app runs on a local Kubernetes cluster (k3d) and is deployed the
GitOps way: **git is the source of truth, and Argo CD makes the cluster
match it.** Terraform sets up the cluster and platform; nobody runs
`helm install` or `kubectl apply` against the app.

```bash
make cluster-up      # k3d, ingress-nginx, CloudNativePG, Argo CD, Kyverno, root app
make gitops-status   # Argo CD Applications: sync, health, deployed revision
make smoke-test      # GET http://tasks.localhost/healthz/ through the ingress
```

See [`infra/README.md`](infra/README.md) for prerequisites and how the
platform is built.

### From `git push` to a running pod

```mermaid
flowchart TB
    dev(["git push / PR merged to main"]) --> ci

    subgraph ci["GitHub Actions (ci.yml)"]
        direction TB
        gates["tests + security gates"] --> changes{"only gitops/<br/>changed?"}
        changes -- "yes: no new image" --> skip(["publish skipped"])
        changes -- no --> build["build + scan amd64 & arm64<br/>push · index · SBOM"]
        build --> sign["cosign sign (keyless)<br/>identity = ci.yml@refs/heads/main"]
        sign --> promote["promote job (GitHub App)<br/>PR: gitops/envs/local values<br/>tag + digest · auto-merge"]
    end

    promote -- "PR passes CI, merges" --> git[("git: gitops/envs/local/<br/>task-manager/values.yaml")]

    subgraph cluster["k3d cluster"]
        direction TB
        argo["Argo CD<br/>root app → platform → db → app<br/>(sync waves, self-heal, prune)"]
        argo --> kyv{"Kyverno admission:<br/>signed by ci.yml on main?"}
        kyv -- no --> deny(["denied: nothing changes"])
        kyv -- yes --> presync["PreSync hook:<br/>migrations Job"]
        presync --> rollout["rolling update<br/>Deployment (HPA 2–4)"]
        rollout --> pod(["running pod<br/>image@sha256:…"])
    end

    git -- "polled every 60s" --> argo
    ghcr[("GHCR<br/>signed multi-arch image")] -.-> kyv
    ghcr -.-> pod
```

### How it fits together

- **`gitops/apps/`**: the Argo CD Applications (app-of-apps). Terraform
  creates one root Application that syncs this folder; it holds:
  - `platform` (sync wave −1): the `task-manager` namespace with the
    enforcement label, the Kyverno admission policies, and the API-server
    backstop policy;
  - `task-manager-db` (wave 0): the CloudNativePG database chart. Its
    Cluster and the namespace are marked `Delete=false,Prune=false`, and
    this Application has no cascade-delete finalizer, so no GitOps action
    can delete the database (see "Protecting stateful resources" in
    `infra/README.md`);
  - `task-manager` (wave 1): the app chart.

  Waves make Argo CD wait for each to be healthy before the next, so
  policies exist before any pod and the database is up before migrations.
- **`gitops/envs/local/`**: the environment's values. The app's
  `image.tag` + `image.digest` live in `task-manager/values.yaml`; pods pull
  `image:tag@digest`, so the tag can never be moved to a different image.
- **Automated sync with self-heal and prune.** Manual changes are reverted
  (for example `kubectl set env`, editing a managed label, or deleting the
  Ingress all come back within about half a minute). Resources removed
  from git are deleted from the cluster.
- **Migrations** run once per sync as a PreSync hook (the chart's Helm
  `pre-install`/`pre-upgrade` hook, which Argo CD maps to PreSync). A failed
  migration stops the sync, so new pods never start on an unmigrated
  database.

### Signature enforcement (Kyverno)

Only images signed by **this repository's `ci.yml` on `main`** may run in
the `task-manager` namespace. Kyverno verifies the cosign keyless signature
(certificate issuer `token.actions.githubusercontent.com`, exact subject
`…/.github/workflows/ci.yml@refs/heads/main`) on every Pod, Deployment and
Job before it's admitted. The CloudNativePG images in the namespace are
verified the same way, against CloudNativePG's own release workflows.
Any other image is denied.

**Defence in depth: git is not trusted blindly.** Even if a wrong or
malicious digest is written into `gitops/` (a compromised account, a bad
merge, a hand-edited values file), the cluster still refuses it, because
that image isn't signed by `ci.yml` on `main`. This was demonstrated on the
`feature/gitops` branch:

1. A commit set `image.digest` to a digest that **does exist in our own
   GHCR repository** but was never signed by CI.
2. Argo CD synced it; Kyverno denied the PreSync migration Job
   (`image is not signed by the expected identity`), so the sync failed
   before the Deployment was touched. The signed version kept serving.
3. `git revert` of that commit brought Argo CD back to Synced/Healthy.

Unsigned images applied by hand are rejected too:

```console
$ kubectl --context k3d-tasks -n task-manager run x --image=python:3.12-slim
Error from server: admission webhook "vpol.validate.kyverno.svc-fail-finegrained-task-manager-allowed-images"
denied the request: Policy task-manager-allowed-images failed: images not allowed in this namespace: python:3.12-slim
```

Policies: [`gitops/platform/policies.yaml`](gitops/platform/policies.yaml),
plus an API-server [backstop](gitops/platform/backstop.yaml) that still
restricts registries and requires digests if Kyverno itself is shut down
(see the Kyverno outage runbook in `infra/README.md`).

### Promotion: CI opens a PR

After `publish` succeeds on `main`, the `promote` job writes the new
`image.tag` (git SHA) and `image.digest` (multi-arch index digest) into
`gitops/envs/local/task-manager/values.yaml`, opens a PR and enables
auto-merge. When CI passes it merges, and Argo CD deploys it.

**Why a PR rather than a direct commit to `main`:**

| | PR + auto-merge (chosen) | Direct commit |
|---|---|---|
| Branch protection | respected | needs a bypass for the bot |
| Audit trail | a PR per promotion, linked to the publish run | a commit |
| Gate | CI runs on the change (including the targetRevision check) | none |
| Rollback | revert the PR's commit | revert the commit |
| Speed | a few minutes (CI) | immediate |

The PR is opened with a **GitHub App** token, not `GITHUB_TOKEN`: PRs
created with `GITHUB_TOKEN` don't trigger workflows, so their required
checks would never run and the PR could never merge. A promotion PR only
changes `gitops/`, so the `changes` job skips publishing: no new image, no
endless build-promote loop.

**One-time setup** (the `promote` job stays off until this is done):

1. **Create a GitHub App** (Settings → Developer settings → GitHub Apps →
   New GitHub App):
   - Name: e.g. `task-manager-promoter`; Homepage URL: this repository.
   - Webhook: **uncheck "Active"** (no webhook needed).
   - Repository permissions: **Contents: Read and write**, **Pull
     requests: Read and write** (Metadata: Read-only is added
     automatically). No other permissions, no account permissions.
   - "Where can this GitHub App be installed?": **Only on this account**.
2. **Generate a private key** on the App's page (downloads a `.pem`), and
   note the **App ID**.
3. **Install the App** on this account, **Only select repositories →
   `django-task-manager`**.
4. **Create the environment**: repository Settings → Environments → New
   environment `promotion`:
   - Deployment branches and tags: **Selected branches → `main`** only.
   - Environment variable `PROMOTION_APP_ID` = the App ID.
   - Environment secret `PROMOTION_APP_PRIVATE_KEY` = the full `.pem`
     contents.
5. **Allow auto-merge**: Settings → General → Pull Requests → **Allow
   auto-merge**.
6. **Turn promotion on**: Settings → Secrets and variables → Actions →
   Variables → repository variable `PROMOTION_ENABLED` = `true`.

Only the `promote` job uses the `promotion` environment, and the
environment only releases its secret to jobs running on `main`. The job
asks the App for just `contents: write` and `pull-requests: write`; the
token expires after an hour.

### Rollback

Revert the promotion commit (through a PR, like any change to `main`):

```bash
git revert <promotion-commit>    # or the "Revert" button on the merged PR
```

Argo CD syncs the previous `image.tag` + `image.digest`. That image is
still signed by `ci.yml` on `main`, so Kyverno admits it, and the migration
hook runs (Django migrations are forward-only: a rollback across a schema
change needs a migration that undoes it).

### Branch-tracking guard

During development the Applications can point at a feature branch so
Argo CD syncs work in progress. The `GitOps manifests check` CI job fails
if any Application in `gitops/apps/` tracks anything other than `main`,
so that setting can't be merged.

### Argo CD UI (no ingress)

The UI is deliberately **not** exposed through the ingress:

```bash
make argocd-password   # admin password (random, from Terraform state)
make argocd-ui         # port-forward → https://localhost:8443, user admin
```

Terraform sets a random admin password from the start, so
`argocd-initial-admin-secret` is never created (and is deleted if it
exists).

### Local, unsigned builds

`task-manager` only runs signed images from GHCR. To try a local build
without going through CI, deploy it to a separate namespace that has no
signature enforcement:

```bash
make build-push dev-deploy   # → task-manager-dev, http://dev.tasks.localhost
```

## REST API

Everything lives under `/api/`. Every task endpoint requires
authentication, and you only ever see your own tasks: another user's
task returns `404 Not Found`.

| Method | URL | What it does |
|---|---|---|
| `POST` | `/api/token/` | Exchange username + password for a token |
| `GET` | `/api/tasks/` | List your tasks (paginated) |
| `POST` | `/api/tasks/` | Create a task |
| `GET` | `/api/tasks/<id>/` | Get one task |
| `PUT` / `PATCH` | `/api/tasks/<id>/` | Replace / partly update a task |
| `DELETE` | `/api/tasks/<id>/` | Delete a task |
| `GET` | `/api/docs/` | Swagger UI (OpenAPI schema at `/api/schema/`) |

### Authentication

**Token** — for scripts and other clients. Get a token once, then send
it in the `Authorization` header:

```bash
curl -X POST http://127.0.0.1:8000/api/token/ \
     -H "Content-Type: application/json" \
     -d '{"username": "alice", "password": "your-password"}'
# {"token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"}

export TOKEN=9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

The token endpoint uses the same per-username lockout as the web login
(5 failed attempts → locked for 15 minutes, answered with `429`), so the
API can't be used to get around it. It is also rate limited per IP
address (`API_TOKEN_THROTTLE_RATE`, default `10/minute`).

**Session** — log in on the website (or at `/api/auth/login/`) and open
`/api/tasks/` in the browser to use DRF's browsable API.

### Examples

Create a task (`priority` is `low`, `medium` or `high`, default `medium`;
`due_date` can't be in the past):

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/ \
     -H "Authorization: Token $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title": "Write report", "description": "Q3 numbers", "due_date": "2026-12-01", "priority": "high"}'
```

```json
{
  "id": 7,
  "title": "Write report",
  "description": "Q3 numbers",
  "due_date": "2026-12-01",
  "priority": "high",
  "completed": false,
  "is_overdue": false,
  "owner": "alice",
  "created_at": "2026-10-29T15:40:12.345678Z",
  "updated_at": "2026-10-29T15:40:12.345678Z"
}
```

List, filter, search and sort:

```bash
# All your tasks, 10 per page
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/tasks/

# Open high-priority tasks, soonest due first
curl -H "Authorization: Token $TOKEN" \
     "http://127.0.0.1:8000/api/tasks/?completed=false&priority=high&ordering=due_date"

# Search titles, highest priority first, page 2
curl -H "Authorization: Token $TOKEN" \
     "http://127.0.0.1:8000/api/tasks/?search=report&ordering=-priority&page=2"
```

List responses are paginated:

```json
{"count": 12, "next": "http://127.0.0.1:8000/api/tasks/?page=2", "previous": null, "results": [ ... ]}
```

| Query parameter | Values |
|---|---|
| `completed` | `true` / `false` |
| `priority` | `low` / `medium` / `high` |
| `search` | text to match in the title (case-insensitive) |
| `ordering` | `due_date`, `priority`, `created_at`; prefix `-` to reverse (default `-created_at`) |
| `page` | page number (10 tasks per page) |
| `all` | `true` — **staff only**: list every user's tasks (ignored for everyone else) |

Update and delete:

```bash
# Mark as done
curl -X PATCH http://127.0.0.1:8000/api/tasks/7/ \
     -H "Authorization: Token $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"completed": true}'

# Delete (returns 204 No Content)
curl -X DELETE http://127.0.0.1:8000/api/tasks/7/ -H "Authorization: Token $TOKEN"
```

Staff listing every user's tasks:

```bash
curl -H "Authorization: Token $STAFF_TOKEN" "http://127.0.0.1:8000/api/tasks/?all=true"
```

`?all=true` only affects listing. Staff still get `404` when reading,
changing or deleting another user's task through the API (use the
Django admin for that).

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
```

Tests run against SQLite and don't need Docker or PostgreSQL.

The suite covers registration (including password hashing and mismatch
rejection), login success/failure, **login throttling** (lockout after
the max attempts, and that a successful login resets the counter),
task create/edit/toggle/delete, dashboard filtering, sorting and
pagination, that users can't view or change each other's tasks,
role-based permission enforcement on the admin view (403 vs 200), and
password reset email delivery.

The API tests (`tasks/test_api.py`) cover authentication (401 without
a token), the token endpoint and its lockout, user isolation (another
user's task is a 404 for read, update and delete), staff `?all=true`,
CRUD and validation, filters, search, ordering, pagination, and the
OpenAPI docs.

`tasks/test_production.py` covers the production setup: `/healthz/`,
the `SECRET_KEY` check, `DATABASE_URL` parsing, the HTTPS settings and
email configuration.

CI (`.github/workflows/ci.yml`) runs the tests, runs `check --deploy`
with production settings, builds the Docker image and starts the compose
stack until it reports healthy, then runs the security gates described
in [Secure CI/CD pipeline](#secure-cicd-pipeline).

## Project structure

```
task_manager_app/
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── SECURITY.md            # vulnerability reporting, pipeline guarantees, accepted findings
├── .github/
│   ├── workflows/ci.yml   # tests, security gates, signed release
│   ├── scripts/           # tool installer (SHA-256 checked), image scan, pip-audit → SARIF
│   └── dependabot.yml
├── Makefile               # local Kubernetes: cluster-up, gitops-status, smoke-test, argocd-ui, dev-deploy
├── infra/                 # Terraform: k3d, ingress-nginx, CNPG, Argo CD, Kyverno (see infra/README.md)
├── deploy/helm/           # Helm charts: task-manager (app), task-manager-db (CNPG)
├── gitops/
│   ├── apps/              # Argo CD Applications (app-of-apps): platform, db, app
│   ├── platform/          # namespace + Kyverno image-signature policies
│   └── envs/local/        # environment values; image tag + digest (bumped by CI)
├── Dockerfile
├── docker-compose.yml     # web + postgres, for running locally
├── docker-entrypoint.sh   # runs migrations, then gunicorn
├── gunicorn.conf.py
├── .env.example
├── pytest.ini
├── conftest.py
├── task_project/          # settings, root urls.py
└── tasks/                 # the app
    ├── models.py           # Task model (linked to Django's User)
    ├── views.py            # register, dashboard, task create/edit/toggle/delete, admin_dashboard
    ├── forms.py            # ThrottledAuthenticationForm, TaskForm
    ├── api/                # REST API: serializers, filters, viewset, token view, urls
    ├── checks.py           # refuses DEBUG=False with the default SECRET_KEY
    ├── admin.py            # Task registered in Django admin
    ├── tests.py            # pytest suite for the web app
    ├── test_api.py         # pytest suite for the REST API
    ├── test_production.py  # pytest suite for the production settings
    └── templates/
        ├── base.html
        ├── 403.html
        ├── registration/   # register, login, password reset chain
        └── tasks/          # dashboard, task_form (edit), admin_dashboard
```

## Notes

- `db.sqlite3` and `.env` are git-ignored — `migrate` recreates the
  database, and you create your own `.env` from `.env.example`.
- The login throttle counter lives in Django's cache framework
  (in-memory by default). In a multi-server deployment you'd back this
  with a shared cache (e.g. Redis) so the count is consistent across
  instances — noted in `tasks/forms.py`.
- `DEBUG` defaults to `False`; set `DEBUG=True` in `.env` for local
  development. Emails go to the console unless `EMAIL_BACKEND` is set to
  SMTP.
- `/livez/` (process up) and `/healthz/` (app + database) are the
  liveness and readiness checks used by Kubernetes.
- `/api/docs/` and `/api/schema/` are public (they describe the API,
  not anyone's data). The Swagger UI loads its JavaScript from a CDN.
