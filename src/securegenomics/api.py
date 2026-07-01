"""
Shared API request helpers for SecureGenomics managers.
"""

from typing import Any

import requests


class AuthenticatedApiClient:
    """Small authenticated request wrapper shared by manager classes."""

    def __init__(self, auth_manager: Any, config_manager: Any, default_timeout: int = 30) -> None:
        self.auth_manager = auth_manager
        self.config_manager = config_manager
        self.default_timeout = default_timeout

    def request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an authenticated API request with consistent mechanics."""
        self._ensure_authenticated()
        headers = self.auth_manager._get_auth_headers()

        if not headers:
            raise Exception("Not authenticated. Please login first.")

        url = f"{self.config_manager.get_server_url()}{endpoint}"

        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers

        kwargs.setdefault("timeout", self.default_timeout)

        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")

    def _ensure_authenticated(self) -> None:
        if not self.auth_manager.is_authenticated():
            raise Exception("Not authenticated. Please login first.")
