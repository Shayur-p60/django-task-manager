FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser . .

# Collect static files into the image. The values below only let the
# settings load during the build; they are not stored in the image.
RUN DEBUG=False SECRET_KEY=collectstatic-build-only \
    python manage.py collectstatic --noinput \
    && chmod +x docker-entrypoint.sh \
    && chown appuser:appuser /app  # lets the SQLite fallback create db.sqlite3

USER appuser

EXPOSE 8000

# Runs migrations, then starts the command below.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Settings (port, workers, logging) are in gunicorn.conf.py.
CMD ["gunicorn", "task_project.wsgi:application"]
