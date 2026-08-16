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
