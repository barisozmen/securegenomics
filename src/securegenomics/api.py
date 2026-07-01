"""
Shared API request helpers for SecureGenomics managers.
"""

from typing import Any, Dict

import requests


class AuthenticatedApiClient:
    """Small authenticated request wrapper shared by manager classes."""

    def __init__(self, auth_manager: Any, config_manager: Any, default_timeout: int = 30) -> None:
        self.auth_manager = auth_manager
        self.config_manager = config_manager
        self.default_timeout = default_timeout

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an API request with shared defaults and optional auth."""
        url = self._build_url(endpoint)
        request_kwargs = self._prepare_request_kwargs(
            kwargs,
            authenticated=authenticated,
        )

        try:
            return requests.request(method, url, **request_kwargs)
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}") from e

    def _ensure_authenticated(self) -> None:
        if not self.auth_manager.is_authenticated():
            raise Exception("Not authenticated. Please login first.")

    def _build_url(self, endpoint: str) -> str:
        return f"{self.config_manager.get_server_url()}{endpoint}"

    def _prepare_request_kwargs(
        self,
        kwargs: Dict[str, Any],
        *,
        authenticated: bool,
    ) -> Dict[str, Any]:
        if authenticated:
            self._merge_headers(kwargs, self._auth_headers())

        kwargs.setdefault("timeout", self.default_timeout)
        # Security invariant: verify TLS and never follow cross-origin redirects
        # with the auth token / request body attached (protects against a
        # 30x that re-sends ciphertext or the bearer token to another origin).
        kwargs.setdefault("verify", True)
        kwargs.setdefault("allow_redirects", False)
        return kwargs

    def _auth_headers(self) -> Dict[str, str]:
        self._ensure_authenticated()
        headers = self.auth_manager._get_auth_headers()

        if not headers:
            raise Exception("Not authenticated. Please login first.")

        return headers

    def _merge_headers(self, kwargs: Dict[str, Any], headers: Dict[str, str]) -> None:
        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers
