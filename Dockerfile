# Base image pinned by digest (multi-arch index) so builds are reproducible
# and a re-pushed tag can't change what we ship. Dependabot updates it.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
# pip is removed afterwards: the app doesn't need it at runtime, and pip
# bundles its own copies of urllib3, msgpack and setuptools, which carry
# vulnerabilities of their own. The non-root user is created in the same layer.
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && pip uninstall --yes pip \
    && useradd --create-home --uid 10001 --user-group appuser

COPY --chown=10001:10001 . .

# Collect static files into the image. The values below only let the
# settings load during the build; they are not stored in the image.
# chown /app lets the SQLite fallback create db.sqlite3.
RUN DEBUG=False SECRET_KEY=collectstatic-build-only \
    python manage.py collectstatic --noinput \
    && chmod +x docker-entrypoint.sh \
    && chown 10001:10001 /app

# Numeric UID/GID so Kubernetes can verify runAsNonRoot without /etc/passwd.
USER 10001:10001

EXPOSE 8000

# Runs `check --deploy`, then migrations, then the command below.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Settings (port, workers, logging) are in gunicorn.conf.py.
CMD ["gunicorn", "task_project.wsgi:application"]
