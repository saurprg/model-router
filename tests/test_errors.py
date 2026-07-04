import httpx
import pytest

from app.errors import FatalError, RetryableError, RouterError
from app.providers.base import map_http_error, map_transport_error


@pytest.mark.parametrize(
    ("status", "expected_type", "expected_code"),
    [
        (400, FatalError, "upstream_bad_request"),
        (401, RetryableError, "upstream_401"),
        (403, RetryableError, "upstream_403"),
        (429, RetryableError, "upstream_429"),
        (502, RetryableError, "upstream_502"),
        (503, RetryableError, "upstream_503"),
        (504, RetryableError, "upstream_504"),
        (500, RetryableError, "upstream_error"),
    ],
)
def test_map_http_error(
    status: int,
    expected_type: type[RouterError],
    expected_code: str,
) -> None:
    exc = map_http_error(status, "upstream body")
    assert isinstance(exc, expected_type)
    assert exc.code == expected_code
    assert "upstream body" in exc.message


def test_map_http_error_empty_body_uses_status() -> None:
    exc = map_http_error(503, "")
    assert exc.code == "upstream_503"
    assert "503" in exc.message


def test_map_transport_error_timeout() -> None:
    exc = map_transport_error(httpx.TimeoutException("timed out"))
    assert isinstance(exc, RetryableError)
    assert exc.code == "upstream_timeout"


def test_map_transport_error_connection() -> None:
    exc = map_transport_error(httpx.ConnectError("connection refused"))
    assert isinstance(exc, RetryableError)
    assert exc.code == "upstream_connection_error"


def test_map_transport_error_generic() -> None:
    exc = map_transport_error(RuntimeError("unexpected"))
    assert isinstance(exc, RetryableError)
    assert exc.code == "upstream_error"
