"""Gunicorn settings. Loaded automatically from the working directory."""
import os

# Render and Railway tell the app which port to use through $PORT.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '30'))

# Log requests and errors to stdout/stderr for Docker and the platform logs.
accesslog = '-'
errorlog = '-'
