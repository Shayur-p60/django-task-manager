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

CI (`.github/workflows/tests.yml`) runs the tests, runs
`check --deploy` with production settings, then builds the Docker image
and starts the compose stack until it reports healthy.

## Project structure

```
task_manager_app/
├── manage.py
├── requirements.txt
├── requirements-dev.txt
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
- `/api/docs/` and `/api/schema/` are public (they describe the API,
  not anyone's data). The Swagger UI loads its JavaScript from a CDN.
