import pytest
from django.test import override_settings


@pytest.fixture(scope="session", autouse=True)
def disable_ssl_redirect_for_tests():
    """Disable SECURE_SSL_REDIRECT for all tests to prevent 301 redirects."""
    with override_settings(SECURE_SSL_REDIRECT=False):
        yield
