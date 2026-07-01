from unittest.mock import Mock, patch

import pytest
import requests

from securegenomics.api import AuthenticatedApiClient


class FakeAuthManager:
    def __init__(self, authenticated=True, headers=None):
        self.authenticated = authenticated
        self.headers = headers or {"Authorization": "Bearer test-token"}

    def is_authenticated(self):
        return self.authenticated

    def _get_auth_headers(self):
        return dict(self.headers)


class FakeConfigManager:
    def __init__(self, server_url="https://example.test"):
        self.server_url = server_url

    def get_server_url(self):
        return self.server_url


def test_authenticated_request_merges_auth_headers_and_keeps_caller_headers():
    client = AuthenticatedApiClient(FakeAuthManager(), FakeConfigManager())
    caller_headers = {"X-Trace-ID": "abc", "Authorization": "Bearer stale-token"}
    response = Mock()

    with patch("securegenomics.api.requests.request", return_value=response) as request:
        result = client.request(
            "POST",
            "/api/projects/",
            headers=caller_headers,
            json={"protocol_name": "demo"},
        )

    assert result is response
    assert request.call_args.args == ("POST", "https://example.test/api/projects/")
    assert request.call_args.kwargs["headers"] == {
        "X-Trace-ID": "abc",
        "Authorization": "Bearer test-token",
    }
    assert request.call_args.kwargs["json"] == {"protocol_name": "demo"}


def test_request_uses_secure_transport_defaults():
    client = AuthenticatedApiClient(FakeAuthManager(), FakeConfigManager())

    with patch("securegenomics.api.requests.request", return_value=Mock()) as request:
        client.request("GET", "/api/status/")

    assert request.call_args.kwargs["verify"] is True
    assert request.call_args.kwargs["allow_redirects"] is False


def test_authenticated_request_uses_custom_default_timeout():
    client = AuthenticatedApiClient(
        FakeAuthManager(),
        FakeConfigManager("https://secure.example"),
        default_timeout=90,
    )

    with patch("securegenomics.api.requests.request", return_value=Mock()) as request:
        client.request("GET", "/api/status/")

    assert request.call_args.kwargs["timeout"] == 90
    assert request.call_args.args[1] == "https://secure.example/api/status/"


def test_authenticated_request_preserves_explicit_timeout():
    client = AuthenticatedApiClient(
        FakeAuthManager(),
        FakeConfigManager(),
        default_timeout=90,
    )

    with patch("securegenomics.api.requests.request", return_value=Mock()) as request:
        client.request("GET", "/api/status/", timeout=5)

    assert request.call_args.kwargs["timeout"] == 5


def test_request_can_skip_authentication_for_basic_request():
    client = AuthenticatedApiClient(
        FakeAuthManager(authenticated=False),
        FakeConfigManager(),
    )

    with patch("securegenomics.api.requests.request", return_value=Mock()) as request:
        client.request(
            "GET",
            "/api/health/",
            authenticated=False,
            headers={"Accept": "application/json"},
        )

    request.assert_called_once_with(
        "GET",
        "https://example.test/api/health/",
        headers={"Accept": "application/json"},
        timeout=30,
        verify=True,
        allow_redirects=False,
    )


def test_authenticated_request_requires_authentication():
    client = AuthenticatedApiClient(FakeAuthManager(authenticated=False), FakeConfigManager())

    with pytest.raises(Exception, match="Not authenticated. Please login first."):
        client.request("GET", "/api/projects/")


def test_authenticated_request_converts_request_exception():
    client = AuthenticatedApiClient(FakeAuthManager(), FakeConfigManager())
    error = requests.RequestException("connection failed")

    with patch(
        "securegenomics.api.requests.request",
        side_effect=error,
    ):
        with pytest.raises(Exception) as exc_info:
            client.request("GET", "/api/projects/")

    assert str(exc_info.value) == "Network error: connection failed"
    assert exc_info.value.__cause__ is error
