import os

import pytest

from app.settings import get_settings


@pytest.fixture(scope="session", autouse=True)
def _require_gateway_api_key() -> None:
    """Settings loads GATEWAY_API_KEY at import; mirror CI env for local runs."""
    os.environ.setdefault("GATEWAY_API_KEY", "test-gateway-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
