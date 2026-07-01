"""Token response and auth-file persistence for SecureGenomics auth."""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from securegenomics.config import ConfigManager


DEFAULT_EXPIRES_IN = 2_592_000
EXPIRY_BUFFER_SECONDS = 300


class TokenPersistence:
    """Persists opaque bearer tokens returned by the Gencrypt Rails API."""

    def __init__(
        self,
        config_manager: ConfigManager,
        auth_file: Path,
        last_email_file: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config_manager = config_manager
        self.auth_file = auth_file
        self.last_email_file = last_email_file
        self.clock = clock

    def store_response(self, data: Dict[str, Any], email: str) -> None:
        """Persist the token body returned by /api/login or /api/register.

        The token is opaque; expiry comes straight from `expires_in` seconds,
        never from decoding the token.
        """
        token = data.get("token") or data.get("access_token")
        if not token:
            raise Exception("Server response did not include an authentication token")

        expires_in = int(data.get("expires_in", DEFAULT_EXPIRES_IN))
        user = data.get("user") or {}
        stored_email = user.get("email") or user.get("email_address") or email

        tokens = {
            "access_token": token,
            "email": stored_email,
            "expires_at": self.clock() + expires_in,
            "user": user,
        }

        self.save(tokens)
        self.config_manager.set_authenticated_user(stored_email)
        self.save_last_email(stored_email)
        self.config_manager.log_audit_event("auth_login", {"email": stored_email})

    def save(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to auth file."""
        try:
            with open(self.auth_file, "w") as f:
                json.dump(tokens, f, indent=2)

            self.auth_file.chmod(0o600)

        except OSError as e:
            raise Exception(f"Could not save authentication tokens: {e}")

    def load(self) -> Optional[Dict[str, Any]]:
        """Load tokens from auth file."""
        if not self.auth_file.exists():
            return None

        try:
            with open(self.auth_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self) -> None:
        """Remove the local auth file if present."""
        if self.auth_file.exists():
            self.auth_file.unlink()

    def current_user_email(self) -> Optional[str]:
        """Get current user's email from stored tokens."""
        tokens = self.load()
        return tokens.get("email") if tokens else None

    def is_expired(self, tokens: Dict[str, Any]) -> bool:
        """Check if the stored token has passed its expiry buffer."""
        expires_at = tokens.get("expires_at", 0)
        return self.clock() > (expires_at - EXPIRY_BUFFER_SECONDS)

    def save_last_email(self, email: str) -> None:
        """Save the last used email for convenience."""
        try:
            with open(self.last_email_file, "w") as f:
                f.write(email)
            self.last_email_file.chmod(0o600)
        except OSError:
            pass

    def load_last_email(self) -> Optional[str]:
        """Load the last used email."""
        try:
            if self.last_email_file.exists():
                with open(self.last_email_file, "r") as f:
                    return f.read().strip()
        except OSError:
            pass
        return None
