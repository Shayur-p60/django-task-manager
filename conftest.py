import pytest


@pytest.fixture(autouse=True)
def clear_cache():
    """
    Ensures the login-throttle counters (stored in Django's cache
    framework) don't leak between tests, since LocMemCache is
    process-wide/shared across test cases by default.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def test_friendly_settings(settings):
    """
    Keep tests independent of the production settings that kick in when
    DEBUG=False (the default):
    - the test client talks plain HTTP, so don't redirect it to HTTPS;
    - use plain static storage so pages render without running
      `collectstatic` first (the manifest storage needs its manifest).
    """
    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        **settings.STORAGES,
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
