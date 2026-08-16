# Task Manager — Django Web App with Authentication

A task manager built with Django covering the full authentication
lifecycle: registration, login (with brute-force throttling), logout,
password reset via email, and role-based permissions.

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

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
```

18 tests cover registration (including password hashing and mismatch
rejection), login success/failure, **login throttling** (lockout after
the max attempts, and that a successful login resets the counter),
task CRUD, that users can't modify each other's tasks, role-based
permission enforcement on the admin view (403 vs 200), and password
reset email delivery. CI runs this suite on every push via GitHub
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
    ├── views.py            # register, dashboard, admin_dashboard
    ├── forms.py            # ThrottledAuthenticationForm
    ├── admin.py            # Task registered in Django admin
    ├── tests.py            # pytest test suite
    └── templates/
        ├── base.html
        ├── 403.html
        ├── registration/   # register, login, password reset chain
        └── tasks/          # dashboard, admin_dashboard
```

## Notes

- `db.sqlite3` and `.env` are git-ignored — `migrate` recreates the
  database, and you create your own `.env` from `.env.example`.
- The login throttle counter lives in Django's cache framework
  (in-memory by default). In a multi-server deployment you'd back this
  with a shared cache (e.g. Redis) so the count is consistent across
  instances — noted in `tasks/forms.py`.
- `DEBUG=True` and the console email backend are fine for local
  development and grading; both should change for a real deployment.
