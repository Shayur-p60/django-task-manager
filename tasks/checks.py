from django.conf import settings
from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured


@register(Tags.security)
def check_secret_key_is_set(app_configs, **kwargs):
    """
    Refuse to run in production (DEBUG=False) with the built-in fallback
    SECRET_KEY, or with no key at all. This runs before `migrate`,
    `runserver` and `check`, so a misconfigured container fails at startup
    instead of serving with a publicly known key.
    """
    if settings.DEBUG:
        return []
    try:
        key = settings.SECRET_KEY
    except ImproperlyConfigured:  # Django raises this for an empty key
        key = ''
    if not key or key == settings.INSECURE_DEFAULT_SECRET_KEY or key.startswith('django-insecure-'):
        return [Error(
            'SECRET_KEY is not set (or is the insecure default) while DEBUG=False.',
            hint=(
                'Set the SECRET_KEY environment variable to a long random string, e.g. '
                'python -c "import secrets; print(secrets.token_urlsafe(50))". '
                'For local development, set DEBUG=True in .env instead.'
            ),
            id='tasks.E001',
        )]
    return []
