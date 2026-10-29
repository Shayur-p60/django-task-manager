#!/bin/sh
set -e

# Refuse to start with an unsafe production configuration, such as the
# built-in SECRET_KEY (tasks.E001) or no real email backend (mail.E001).
# This always runs, even when RUN_MIGRATIONS=0 below.
echo "Checking deployment settings..."
python manage.py check --deploy --fail-level ERROR

# Apply migrations on startup. Set RUN_MIGRATIONS=0 to skip, e.g. when
# several instances start at once and migrations run as a separate step.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

exec "$@"
