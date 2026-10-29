"""
Tests for the production setup: health check, SECRET_KEY check,
DATABASE_URL parsing, email configuration and security settings.
"""

import importlib
import os
import sys
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.core import mail
from django.urls import reverse

from .checks import check_secret_key_is_set


# --- Health check ---

@pytest.mark.django_db
def test_healthz_ok(client):
    response = client.get(reverse('healthz'))
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


@pytest.mark.django_db
def test_healthz_reports_database_failure(client):
    with mock.patch('tasks.views.connection.cursor', side_effect=Exception('db down')):
        response = client.get(reverse('healthz'))
    assert response.status_code == 503
    assert response.json()['status'] == 'error'


def test_healthz_is_exempt_from_https_redirect(settings, client):
    # The real production value, restored over the test fixture's override.
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
    with mock.patch('tasks.views.connection.cursor'):
        assert client.get('/healthz/').status_code == 200
    assert client.get('/login/').status_code == 301


# --- SECRET_KEY check ---

def test_secret_key_check_fails_with_default_key_in_production(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = settings.INSECURE_DEFAULT_SECRET_KEY
    errors = check_secret_key_is_set(None)
    assert [e.id for e in errors] == ['tasks.E001']


@pytest.mark.parametrize('key', ['', 'django-insecure-abc123'])
def test_secret_key_check_fails_with_empty_or_insecure_key(settings, key):
    settings.DEBUG = False
    settings.SECRET_KEY = key
    assert [e.id for e in check_secret_key_is_set(None)] == ['tasks.E001']


def test_secret_key_check_passes_with_real_key(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = 'x7Gk2-real-looking-random-secret-key-0123456789abcdefghij'
    assert check_secret_key_is_set(None) == []


def test_secret_key_check_skipped_in_debug(settings):
    settings.DEBUG = True
    settings.SECRET_KEY = settings.INSECURE_DEFAULT_SECRET_KEY
    assert check_secret_key_is_set(None) == []


# --- Settings module under different environments ---

SETTINGS_MODULE = 'task_project.settings'
ENV_PREFIXES = ('DATABASE_URL', 'EMAIL_', 'DEFAULT_FROM_EMAIL', 'USE_HTTPS', 'SECURE_',
                'ALLOW_CONSOLE_EMAIL', 'NUM_PROXIES')


def load_settings(**env):
    """Import a fresh copy of the settings module with the given environment."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(ENV_PREFIXES)}
    clean_env.update({'DEBUG': 'False', 'SECRET_KEY': 'test-key-' + 'x' * 50})
    clean_env.update(env)
    with mock.patch.dict(os.environ, clean_env, clear=True):
        sys.modules.pop(SETTINGS_MODULE, None)
        return importlib.import_module(SETTINGS_MODULE)


@pytest.fixture(autouse=True)
def restore_settings_module():
    original = sys.modules.get(SETTINGS_MODULE)
    yield
    if original is not None:
        sys.modules[SETTINGS_MODULE] = original


def test_database_defaults_to_sqlite():
    s = load_settings()
    assert s.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
    assert str(s.DATABASES['default']['NAME']).endswith('db.sqlite3')


def test_database_url_selects_postgres():
    s = load_settings(DATABASE_URL='postgres://tasks:secret@db:5432/tasks')
    db = s.DATABASES['default']
    assert db['ENGINE'] == 'django.db.backends.postgresql'
    assert (db['HOST'], db['PORT'], db['NAME'], db['USER']) == ('db', 5432, 'tasks', 'tasks')
    assert db['CONN_HEALTH_CHECKS'] is True


def test_production_security_settings_when_debug_off():
    s = load_settings()
    assert s.SECURE_SSL_REDIRECT is True
    assert s.SESSION_COOKIE_SECURE is True
    assert s.CSRF_COOKIE_SECURE is True
    assert s.SECURE_HSTS_SECONDS > 0
    assert s.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert s.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https')


def test_use_https_false_relaxes_https_only_settings():
    s = load_settings(USE_HTTPS='False')
    assert s.SECURE_SSL_REDIRECT is False
    assert s.SESSION_COOKIE_SECURE is False
    assert s.SECURE_HSTS_SECONDS == 0


def test_debug_mode_has_no_https_settings():
    s = load_settings(DEBUG='True')
    assert not hasattr(s, 'SECURE_PROXY_SSL_HEADER')
    assert not hasattr(s, 'SECURE_SSL_REDIRECT')
    assert not hasattr(s, 'SESSION_COOKIE_SECURE')


def test_email_defaults_to_console():
    s = load_settings()
    assert s.MAILERS == {'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}}


def test_email_smtp_from_env():
    s = load_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com', EMAIL_PORT='2525',
        EMAIL_HOST_USER='apikey', EMAIL_HOST_PASSWORD='pw', EMAIL_USE_TLS='True',
        DEFAULT_FROM_EMAIL='Tasks <tasks@example.com>',
    )
    options = s.MAILERS['default']['OPTIONS']
    assert options['host'] == 'smtp.example.com'
    assert options['port'] == 2525
    assert options['username'] == 'apikey'
    assert options['use_tls'] is True
    assert s.DEFAULT_FROM_EMAIL == 'Tasks <tasks@example.com>'


@pytest.mark.django_db
def test_password_reset_email_uses_default_from_email(client, settings, django_user_model):
    settings.DEFAULT_FROM_EMAIL = 'Tasks <tasks@example.com>'
    django_user_model.objects.create_user(username='dana', email='dana@example.com', password='x')
    client.post(reverse('password_reset'), {'email': 'dana@example.com'})
    assert mail.outbox[0].from_email == 'Tasks <tasks@example.com>'


def test_static_files_use_whitenoise():
    assert 'whitenoise.middleware.WhiteNoiseMiddleware' in django_settings.MIDDLEWARE
    middleware = django_settings.MIDDLEWARE
    assert middleware.index('whitenoise.middleware.WhiteNoiseMiddleware') == \
        middleware.index('django.middleware.security.SecurityMiddleware') + 1


def test_console_email_check_is_not_silenced_by_default():
    s = load_settings()
    assert 'mail.E001' not in s.SILENCED_SYSTEM_CHECKS


def test_allow_console_email_silences_only_the_email_check():
    s = load_settings(ALLOW_CONSOLE_EMAIL='True')
    assert 'mail.E001' in s.SILENCED_SYSTEM_CHECKS
    assert 'tasks.E001' not in s.SILENCED_SYSTEM_CHECKS


def test_num_proxies_unset_by_default():
    assert load_settings().REST_FRAMEWORK['NUM_PROXIES'] is None


def test_num_proxies_from_env():
    assert load_settings(NUM_PROXIES='1').REST_FRAMEWORK['NUM_PROXIES'] == 1
