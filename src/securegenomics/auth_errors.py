"""Error response parsing for SecureGenomics authentication/API calls."""

from typing import Optional

import requests


FIELD_MESSAGE_ONLY = {"project_id", "email", "password"}


def parse_error_response(response: requests.Response) -> str:
    """Parse an error body into a human-readable message.

    Prefers the Gencrypt Rails shape ``{error: {code, message, details?}}``.
    Falls back to DRF-style bodies (``detail`` / ``non_field_errors`` /
    field arrays) as a generic legacy safety net for any non-Rails error body.
    """
    try:
        error_data = response.json()
    except (ValueError, TypeError):
        return _non_json_error_message(response)

    # Rails canonical shape: {"error": {"code", "message", "details"?}}
    if isinstance(error_data, dict) and isinstance(error_data.get("error"), dict):
        err = error_data["error"]
        message = err.get("message") or err.get("code") or "Request failed"
        details = err.get("details")
        if details:
            message = f"{message} ({flatten_details(details)})"
        return message

    # Legacy/plain string error value.
    if isinstance(error_data, dict) and isinstance(error_data.get("error"), str):
        return error_data["error"]

    # DRF-style generic legacy fallback (non-Rails error bodies).
    if isinstance(error_data, dict) and "detail" in error_data:
        return error_data["detail"]

    if isinstance(error_data, dict):
        error_messages = _drf_field_messages(error_data)
        if error_messages:
            return "; ".join(error_messages)

    return f"Request failed with status code: {response.status_code}"


def parse_error_code(response: requests.Response) -> Optional[str]:
    """Return the Rails ``error.code`` string if present, else ``None``."""
    try:
        error_data = response.json()
    except (ValueError, TypeError):
        return None

    if isinstance(error_data, dict) and isinstance(error_data.get("error"), dict):
        return error_data["error"].get("code")
    return None


def flatten_details(details) -> str:
    """Render Rails error.details (dict or list) into a compact string."""
    if isinstance(details, dict):
        parts = []
        for field, msgs in details.items():
            if isinstance(msgs, (list, tuple)):
                parts.append(f"{field}: {', '.join(str(m) for m in msgs)}")
            else:
                parts.append(f"{field}: {msgs}")
        return "; ".join(parts)

    if isinstance(details, (list, tuple)):
        return ", ".join(str(m) for m in details)

    return str(details)


def _non_json_error_message(response: requests.Response) -> str:
    error_msg = f"Request failed with status code: {response.status_code}"
    if (
        response.text
        and len(response.text) < 300
        and not response.text.strip().startswith("<")
    ):
        error_msg += f": {response.text.strip()}"
    return error_msg


def _drf_field_messages(error_data: dict) -> list[str]:
    error_messages = []
    if "non_field_errors" in error_data:
        error_messages.extend(error_data["non_field_errors"])

    for field, messages in error_data.items():
        if field in ("non_field_errors", "error"):
            continue
        if isinstance(messages, list):
            for message in messages:
                error_messages.append(_field_message(error_data, field, message))
        else:
            error_messages.append(_field_message(error_data, field, messages))

    return error_messages


def _field_message(error_data: dict, field: str, message) -> str:
    if field in FIELD_MESSAGE_ONLY and len(error_data) == 1:
        return str(message)
    return f"{field}: {message}"
