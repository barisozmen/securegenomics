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


def test_authenticated_request_adds_auth_headers_and_keeps_caller_headers():
    client = AuthenticatedApiClient(FakeAuthManager(), FakeConfigManager())
    response = Mock()

    with patch("securegenomics.api.requests.request", return_value=response) as request:
        result = client.request(
            "POST",
            "/api/projects/",
            headers={"X-Trace-ID": "abc"},
            json={"protocol_name": "demo"},
        )

    assert result is response
    request.assert_called_once_with(
        "POST",
        "https://example.test/api/projects/",
        headers={"X-Trace-ID": "abc", "Authorization": "Bearer test-token"},
        json={"protocol_name": "demo"},
        timeout=30,
    )


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


def test_authenticated_request_requires_authentication():
    client = AuthenticatedApiClient(FakeAuthManager(authenticated=False), FakeConfigManager())

    with pytest.raises(Exception, match="Not authenticated. Please login first."):
        client.request("GET", "/api/projects/")


def test_authenticated_request_converts_request_exception():
    client = AuthenticatedApiClient(FakeAuthManager(), FakeConfigManager())

    with patch(
        "securegenomics.api.requests.request",
        side_effect=requests.RequestException("connection failed"),
    ):
        with pytest.raises(Exception, match="Network error: connection failed"):
            client.request("GET", "/api/projects/")
