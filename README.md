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
- **Secrets kept out of source control** — `SECRET_KEY`, `DEBUG`, and
  `ALLOWED_HOSTS` are read from environment variables via
  `python-decouple`, not hardcoded in `settings.py`.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit .env with your own SECRET_KEY

python manage.py migrate
python manage.py createsuperuser   # creates a staff/admin account
python manage.py runserver
```

Then visit `http://127.0.0.1:8000/register/` to create a regular
account, or log in with the superuser you created to see the admin
dashboard at `/admin-dashboard/`.

### Trying the password reset flow locally

1. Go to `/password-reset/` and enter an existing account's email.
2. Check the terminal running `runserver` — the "email" prints there
   instead of actually being sent (Django's default console mailer).
3. Copy the reset link into your browser to set a new password.

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
OpenAPI docs. CI runs this suite on every push via GitHub
Actions (`.github/workflows/tests.yml`).

## Project structure

```
task_manager_app/
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── pytest.ini
├── conftest.py
├── task_project/          # settings, root urls.py
└── tasks/                 # the app
    ├── models.py           # Task model (linked to Django's User)
    ├── views.py            # register, dashboard, task create/edit/toggle/delete, admin_dashboard
    ├── forms.py            # ThrottledAuthenticationForm, TaskForm
    ├── api/                # REST API: serializers, filters, viewset, token view, urls
    ├── admin.py            # Task registered in Django admin
    ├── tests.py            # pytest suite for the web app
    ├── test_api.py         # pytest suite for the REST API
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
  development. The console email backend is fine locally but should
  change for a real deployment.
- `/api/docs/` and `/api/schema/` are public (they describe the API,
  not anyone's data). The Swagger UI loads its JavaScript from a CDN.
