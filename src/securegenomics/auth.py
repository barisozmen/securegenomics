"""
Authentication management for SecureGenomics CLI.

Handles user authentication, opaque bearer-token management, and server
communication against the Gencrypt (gencrypt.xyz) Rails API.

The token returned by /api/login and /api/register is an opaque, HMAC-signed
Session id — NOT a JWT. Never decode it; derive its expiry from the
`expires_in` field the server returns. There is no refresh endpoint: on expiry
or any 401 the user simply runs `secgen login` again.

Git-style auth UX: login once, persistent until explicit logout.
"""

import getpass
import re
from typing import Any, Dict, Optional

import requests
from rich.console import Console
from rich.prompt import Prompt, Confirm

from securegenomics import __version__
from securegenomics.auth_errors import (
    flatten_details,
    parse_error_code,
    parse_error_response,
)
from securegenomics.auth_tokens import TokenPersistence
from securegenomics.config import ConfigManager

console = Console()

# Sent on every request so ciphertext/token calls are identifiable server-side
# (Rails tags CLI sessions with this User-Agent) and always negotiate JSON.
USER_AGENT = f"securegenomics-cli/{__version__}"


def base_headers() -> Dict[str, str]:
    """Baseline headers for every server call (no auth)."""
    return {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }


class AuthManager:
    """Manages authentication and opaque bearer tokens.

    The stored token is an opaque, HMAC-signed Session id returned by the
    Gencrypt Rails API — NOT a JWT. It is never decoded; its expiry comes from
    the server's ``expires_in`` field.
    """
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.auth_file = self.config_manager.auth_file
        self.server_url = self.config_manager.get_server_url()
        self.last_email_file = self.config_manager.config_dir / "last_email"
        self.token_persistence = TokenPersistence(
            self.config_manager,
            self.auth_file,
            self.last_email_file,
        )
    
    def interactive_login(self) -> bool:
        """Interactive login with secure password input."""
        try:
            console.print("\n[bold blue]SecureGenomics Login[/bold blue]")
            
            # Get email (with memory of last used email)
            email = self._get_email_interactive()
            if not email:
                return False
            
            # Get password securely
            password = self._get_password_secure("Password")
            if not password:
                return False
            
            return self.login(email, password)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Login cancelled[/yellow]")
            return False
        except Exception as e:
            console.print(f"\n[red]Login error: {e}[/red]")
            return False
    
    def interactive_register(self) -> bool:
        """Interactive registration with elegant validation."""
        try:
            console.print("\n[bold green]SecureGenomics Registration[/bold green]")
            
            if not (email := self._get_validated_email()):
                return False
            
            if not (password := self._get_password_with_confirmation()):
                return False
            
            return self.register(email, password)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Registration cancelled[/yellow]")
            return False
        except Exception as e:
            console.print(f"\n[red]Registration error: {e}[/red]")
            return False
    
    def login(self, email: str, password: str) -> bool:
        """Login to the Gencrypt server and store the opaque bearer token."""
        try:
            url = f"{self.server_url}/api/login"
            response = requests.post(
                url,
                json={"email": email, "password": password},
                headers=base_headers(),
                timeout=30,
                allow_redirects=False,
            )

            # Rails returns 201 (a Session is created). Accept 200 too for safety.
            if response.status_code in (200, 201):
                self._store_token_response(response.json(), email)
                return True

            error_msg = self._parse_error_response(response)
            raise Exception(error_msg)

        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
        except Exception as e:
            raise Exception(f"Login failed: {e}")

    def register(self, email: str, password: str) -> bool:
        """Register a new Gencrypt account.

        Rails returns the full token body on 201, so we store the token
        directly instead of doing a second login round-trip.
        """
        try:
            response = requests.post(
                f"{self.server_url}/api/register",
                json={"email": email, "password": password},
                headers=base_headers(),
                timeout=30,
                allow_redirects=False,
            )

            if response.status_code in (200, 201):
                self._store_token_response(response.json(), email)
                return True

            error_msg = self._parse_error_response(response)
            raise Exception(error_msg)

        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
        except Exception as e:
            raise Exception(f"Registration failed: {e}")

    def _store_token_response(self, data: Dict, email: str) -> None:
        """Persist the token body returned by /api/login or /api/register."""
        self.token_persistence.store_response(data, email)
    
    def login_with_stored_credentials(self) -> bool:
        """Attempt login with stored credentials (if available)."""
        # This would integrate with system keychain in production
        # For now, just check if we have valid tokens
        return self.is_authenticated()
    
    def _get_email_interactive(self) -> Optional[str]:
        """Get email with smart defaults and graceful validation."""
        if last_email := self._load_last_email():
            if Confirm.ask(f"Use {last_email}?", console=console, default=True):
                return last_email
        
        return self._get_validated_email()
    
    def _get_password_secure(self, prompt: str = "Password") -> Optional[str]:
        """Get password with secure input (hidden)."""
        try:
            # Use getpass for secure password input
            password = getpass.getpass(f"{prompt}: ")
            return password.strip() if password else None
        except (EOFError, KeyboardInterrupt):
            return None
    
    def _get_password_with_confirmation(self) -> Optional[str]:
        """Elegantly get password with confirmation."""
        for _ in range(3):
            if not (password := self._get_password_secure("Choose password")):
                return None
            
            if len(password) < 8:
                console.print("[dim red]↳ Password must be at least 8 characters[/dim red]")
                continue
            
            if not (confirm := self._get_password_secure("Confirm password")):
                return None
            
            if password == confirm:
                return password
            
            console.print("[dim red]↳ Passwords don't match[/dim red]")
        
        console.print("[dim]Too many attempts. Please try again later.[/dim]")
        return None

    def _validate_email(self, email: str) -> tuple[bool, str]:
        """Elegant email validation returning (is_valid, hint)."""
        if not (email := email.strip()):
            return False, "Email cannot be empty"
        
        # Norvig-style: combine all patterns into one elegant check
        patterns = [
            (r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', "Invalid format (try: name@domain.com)"),
            (r'^[^.@].*[^.@]$', "Cannot start or end with . or @"),
            (r'^[^@]*@[^@]*$', "Must contain exactly one @ symbol"),
            (r'^(?!.*\.\.).*$', "Cannot contain consecutive dots"),
            (r'^(?!.*@\.)(?!.*\.@).*$', "Dots cannot be adjacent to @"),
            (r'^.{1,254}$', "Too long (max 254 characters)")
        ]
        
        for pattern, hint in patterns:
            if not re.match(pattern, email):
                return False, hint
        
        return True, ""

    def _get_validated_email(self, prompt: str = "Email address") -> Optional[str]:
        """Elegantly prompt for email with gentle validation."""
        for attempt in range(5):
            if email := Prompt.ask(prompt, console=console):
                is_valid, hint = self._validate_email(email)
                if is_valid:
                    return email
                console.print(f"[dim red]↳ {hint}[/dim red]")
            else:
                return None
        
        console.print("[dim]Too many attempts. Please try again later.[/dim]")
        return None
    
    def _parse_error_response(self, response: requests.Response) -> str:
        """Parse an error body into a human-readable message."""
        return parse_error_response(response)

    def _flatten_details(self, details) -> str:
        """Render Rails error.details (dict or list) into a compact string."""
        return flatten_details(details)

    def _parse_error_code(self, response: requests.Response) -> Optional[str]:
        """Return the Rails ``error.code`` string if present, else ``None``."""
        return parse_error_code(response)
    
    def _save_last_email(self, email: str) -> None:
        """Save the last used email for convenience."""
        self.token_persistence.save_last_email(email)
    
    def _load_last_email(self) -> Optional[str]:
        """Load the last used email."""
        return self.token_persistence.load_last_email()
    
    def logout(self) -> None:
        """Logout: revoke the server session (best-effort), then wipe local auth."""
        # Log audit event (before clearing tokens)
        user_email = self.get_current_user_email()
        self.config_manager.log_audit_event("auth_logout", {"email": user_email})

        # Best-effort server-side revocation so the Session row is destroyed.
        # Network/HTTP failures must never block a local logout.
        headers = self._auth_headers_if_available()
        if headers:
            try:
                requests.delete(
                    f"{self.server_url}/api/logout",
                    headers=headers,
                    timeout=10,
                    allow_redirects=False,
                )
            except requests.RequestException:
                pass
            except Exception:
                pass

        self.token_persistence.clear()

        # Clear authenticated user from config manager
        self.config_manager.clear_authenticated_user()

    def whoami(self) -> Optional[Dict[str, str]]:
        """Get current user information as ``{"email": ...}``."""
        tokens = self._load_tokens()
        if not tokens:
            return None

        cached_email = tokens.get("email", "unknown")

        # Try to get the fresh profile from the server.
        try:
            headers = self._get_auth_headers()
            if not headers:
                return {"email": cached_email}

            response = requests.get(
                f"{self.server_url}/api/profile",
                headers=headers,
                timeout=10,
                allow_redirects=False,
            )

            if response.status_code == 200:
                try:
                    email = response.json().get("user", {}).get("email")
                except (ValueError, TypeError):
                    email = None
                return {"email": email or cached_email}

            # Token might be expired/revoked; fall back to cached email.
            return {"email": cached_email}

        except requests.RequestException:
            # Network error, return cached email
            return {"email": cached_email}

    def delete_profile(self) -> bool:
        """Account deletion is not available from the CLI yet.

        The Gencrypt API exposes no account-deletion endpoint. Degrade
        gracefully instead of hitting a 404 or crashing.
        """
        console.print(
            "[yellow]Account deletion isn't available from the CLI yet.[/yellow]"
        )
        console.print(
            "Manage or delete your account at [blue]https://gencrypt.xyz/settings[/blue]."
        )
        return False

    def get_token(self) -> Optional[str]:
        """Return the stored bearer token, or ``None`` if missing/expired.

        There is no refresh flow: the token is a 30-day opaque Session id. When
        it expires or is revoked the user re-runs ``secgen login``.
        """
        tokens = self._load_tokens()
        if not tokens:
            return None

        if self._is_token_expired(tokens):
            console.print(
                "[yellow]Session expired or revoked. Run: secgen login[/yellow]"
            )
            return None

        return tokens.get("access_token")

    def _get_auth_headers(self) -> Optional[Dict[str, str]]:
        """Get authorization + base headers for authenticated API requests."""
        token = self.get_token()
        if not token:
            return None

        headers = base_headers()
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _auth_headers_if_available(self) -> Optional[Dict[str, str]]:
        """Auth headers built from a stored (possibly expired) token, no prompts.

        Used by logout's best-effort revocation, where we still want to try to
        destroy the server Session even if the local expiry has lapsed.
        """
        tokens = self._load_tokens()
        if not tokens or not tokens.get("access_token"):
            return None
        headers = base_headers()
        headers["Authorization"] = f"Bearer {tokens['access_token']}"
        return headers
    
    def get_current_user_email(self) -> Optional[str]:
        """Get current user's email from stored tokens."""
        return self.token_persistence.current_user_email()
    
    def _save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to auth file."""
        self.token_persistence.save(tokens)
    
    def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load tokens from auth file."""
        return self.token_persistence.load()
    
    def _is_token_expired(self, tokens: Dict[str, Any]) -> bool:
        """Check if the stored token has passed its expiry (5-minute buffer)."""
        return self.token_persistence.is_expired(tokens)

    def is_authenticated(self) -> bool:
        """Silent predicate: True iff a stored, unexpired token exists.

        Unlike ``get_token`` this never prints, so it's safe for frequent checks.
        """
        tokens = self._load_tokens()
        return bool(tokens) and not self._is_token_expired(tokens)
    
    def _log_audit_event(self, event_type: str, **kwargs) -> None:
        """Log audit event with consistent structure."""
        self.config_manager.log_audit_event(event_type, kwargs)
    
    def _make_api_request(self, method: str, endpoint: str, require_auth: bool = True, **kwargs) -> requests.Response:
        """Make API request with consistent error handling."""
        url = f"{self.server_url}{endpoint}"
        
        # Add auth headers if required and available
        if require_auth:
            headers = self._get_auth_headers()
            if not headers:
                raise Exception("Not authenticated. Please login first.")
            
            if 'headers' in kwargs:
                kwargs['headers'].update(headers)
            else:
                kwargs['headers'] = headers
        
        # Set default timeout if not provided
        kwargs.setdefault('timeout', 30)
        # Never follow cross-origin redirects with the body/token attached.
        kwargs.setdefault('allow_redirects', False)

        try:
            response = requests.request(method, url, **kwargs)
            return response
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
