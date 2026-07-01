"""
Configuration management for SecureGenomics CLI.

Handles configuration files, directory setup, and system status checks.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import time

import requests
from rich.console import Console

console = Console()

# The server the CLI talks to is PINNED to this URL. It is never sourced from a
# per-user config.json, so a stale/old server_url can never misdirect the CLI.
# The only override is the SECUREGENOMICS_SERVER_URL env var (dev/self-host),
# which still passes through enforce_https().
DEFAULT_SERVER_URL = "https://gencrypt.xyz"

# Only literal loopback addresses may be reached over plain http. Anything else
# (including mDNS-spoofable *.local names) must use TLS so that ciphertext and
# bearer tokens never traverse the network in cleartext.
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def enforce_https(server_url: str) -> str:
    """Return server_url unchanged if it is safe to send secrets to, else raise.

    https is always allowed. Plain http is allowed only for literal loopback
    hosts (localhost / 127.0.0.1 / ::1) used in local development. Everything
    else is rejected so no ciphertext or token is ever sent cleartext.
    """
    parsed = urlparse(server_url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme == "https":
        return server_url

    if scheme == "http" and host in LOOPBACK_HOSTS:
        return server_url

    raise ValueError(
        f"Refusing to use insecure server_url {server_url!r}: HTTPS is required "
        f"for any non-loopback host (only http://localhost, http://127.0.0.1, "
        f"and http://[::1] are allowed for local development). "
        f"Set SECUREGENOMICS_SERVER_URL to an https:// URL, or unset it to use "
        f"{DEFAULT_SERVER_URL}."
    )


# Guard so the "non-default server" notice prints at most once per process.
_non_default_server_warned = False


def warn_if_non_default_server() -> None:
    """Print a one-line notice (once per process) when the CLI is pointed at a
    non-default SecureGenomics server.

    Guards against silently sending tokens/ciphertext to a non-gencrypt host:
    whenever get_server_url() resolves to anything other than the pinned
    DEFAULT_SERVER_URL (i.e. a SECUREGENOMICS_SERVER_URL override is in effect),
    surface it once. No-op for the pinned default and after the first call. A
    rejected env override (bad http) is left for the manager boundary to report
    — this never raises.
    """
    global _non_default_server_warned
    if _non_default_server_warned:
        return

    try:
        server_url = ConfigManager().get_server_url()
    except ValueError:
        # Invalid override — enforce_https rejected it. _build_manager surfaces
        # the clean error; don't double-report or crash the warning path.
        return

    if server_url == DEFAULT_SERVER_URL:
        return

    _non_default_server_warned = True
    console.print(
        f"⚠ Using non-default SecureGenomics server: {server_url}",
        style="yellow dim",
    )


class ConfigManager:
    """Manages CLI configuration and system setup."""
    
    def __init__(self) -> None:
        # Base config directory - always exists
        self.base_config_dir = Path.home() / ".securegenomics"
        
        # Initially use unauthenticated paths
        self._current_user = None
        self._setup_paths()
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Try to get authenticated user and update paths if possible
        self._update_user_from_auth()
        
        # Default configuration.
        # NOTE: server_url is deliberately absent — the server is pinned by
        # get_server_url() and must never be sourced from config.json, so it is
        # never a merged config key that a file could shadow.
        self.default_config = {
            "github_org": "securegenomics",
            "protocol_timeout": 300,  # 5 minutes
            "upload_chunk_size": 1024 * 1024,  # 1MB
            "output_format": "human",  # human, json, quiet
            "auto_verify_protocols": True,
            "max_parallel_uploads": 3,
            "crypto_context_upload_timeout": 300,  # 5 minutes for large crypto context uploads
        }
    
    def _setup_paths(self) -> None:
        """Setup file paths based on current user state."""
        if self._current_user:
            # Authenticated user - use email-based directory
            user_id = self._sanitize_username(self._current_user)
            self.config_dir = self.base_config_dir / user_id
        else:
            # Unauthenticated - use temporary shared space
            self.config_dir = self.base_config_dir / ".unauthenticated"
        
        self.auth_file = self.config_dir / "auth.json"
        self.config_file = self.config_dir / "config.json"
        self.audit_log = self.config_dir / "audit.log"
        self.protocols_dir = self.config_dir / "protocols"
        self.crypto_context_dir = self.config_dir / "crypto_context"
        self.projects_dir = self.config_dir / "projects"
    
    def _sanitize_username(self, email: str) -> str:
        """Convert email to safe directory name."""
        # Use first part of email + hash for uniqueness while keeping it readable
        local_part = email.split('@')[0]
        # Clean local part for filesystem safety
        clean_local = ''.join(c for c in local_part if c.isalnum() or c in '-_')
        # Add hash suffix to ensure uniqueness
        email_hash = hashlib.md5(email.encode()).hexdigest()[:8]
        return f"{clean_local}_{email_hash}"
    
    def _update_user_from_auth(self) -> None:
        """Try to get current user from existing auth tokens across all user directories."""
        # Use the class method to find the most recent authenticated user
        most_recent_user = self.find_most_recent_authenticated_user()
        if most_recent_user:
            self.set_authenticated_user(most_recent_user)
    
    def set_authenticated_user(self, email: str) -> None:
        """
        Update configuration to use authenticated user's directory.
        Should be called after successful authentication.
        """
        old_config_dir = self.config_dir
        old_user = self._current_user
        
        self._current_user = email
        self._setup_paths()
        
        # If user changed, migrate data
        if old_user != email and old_config_dir != self.config_dir:
            self._migrate_user_data(old_config_dir, self.config_dir)
        
        # Ensure new directories exist
        self._ensure_directories()
    
    def get_current_user(self) -> Optional[str]:
        """Get the current authenticated user's email."""
        return self._current_user
    
    def _migrate_user_data(self, old_dir: Path, new_dir: Path) -> None:
        """Migrate user data from old directory to new directory."""
        if not old_dir.exists() or old_dir == new_dir:
            return
        
        import shutil
        
        # Create new directory
        new_dir.mkdir(parents=True, exist_ok=True)
        
        # Move files and directories
        for item in old_dir.iterdir():
            if item.name.startswith('.'):
                continue  # Skip hidden files
            
            dest = new_dir / item.name
            if not dest.exists():
                shutil.move(str(item), str(dest))
        
        # Clean up old directory if empty
        try:
            if not any(old_dir.iterdir()):
                old_dir.rmdir()
        except OSError:
            pass  # Directory not empty or other issue
    
    def clear_authenticated_user(self) -> None:
        """Clear authenticated user and revert to unauthenticated state."""
        self._current_user = None
        self._setup_paths()
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        dirs_to_create = [
            self.base_config_dir,  # Ensure base directory exists
            self.config_dir,
            self.protocols_dir,
            self.crypto_context_dir,
            self.projects_dir,
        ]
        
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration, creating default if needed.

        The server URL is deliberately NOT part of this config: it is pinned by
        get_server_url() and must never be sourced from the on-disk config.json.
        Any server_url planted in the file is dropped here so no caller reading
        get_config()["server_url"] can ever be misdirected by a file.
        """
        if not self.config_file.exists():
            return self.default_config.copy()

        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)

            # Merge with defaults to ensure all keys exist
            merged_config = self.default_config.copy()
            merged_config.update(config)
            # A file-planted server_url is never authoritative — the server is
            # pinned by get_server_url(). Drop it so nothing downstream reads it.
            merged_config.pop("server_url", None)
            return merged_config

        except (json.JSONDecodeError, OSError) as e:
            console.print(f"Warning: Could not read config file: {e}")
            return self.default_config.copy()
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except OSError as e:
            raise Exception(f"Could not save config: {e}")
    
    def get_server_url(self) -> str:
        """Return the PINNED server URL — never sourced from config.json.

        The server is hardcoded to DEFAULT_SERVER_URL so a stale/old server_url
        left in a per-user config.json can never misdirect the CLI. The ONLY
        override is the SECUREGENOMICS_SERVER_URL env var (for dev/self-host),
        which still passes through enforce_https().
        """
        override = os.getenv("SECUREGENOMICS_SERVER_URL")
        if override:
            return enforce_https(override)
        return DEFAULT_SERVER_URL
    
    def get_github_org(self) -> str:
        """Get the GitHub organization for protocols."""
        config = self.get_config()
        return config["github_org"]
    
    def get_crypto_context_upload_timeout(self) -> int:
        """Get the timeout for crypto context uploads."""
        config = self.get_config()
        return config.get("crypto_context_upload_timeout", 300)
    
    def get_protocol_timeout(self) -> int:
        """Get the general protocol timeout."""
        config = self.get_config()
        return config.get("protocol_timeout", 300)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        config = self.get_config()
        
        # Check server connectivity. 200/401 both mean the server is up (401 =
        # up but unauthenticated). Redirects are not followed so a mis-pointed
        # host can't silently bounce the probe to another origin.
        server_connected = False
        try:
            response = requests.get(
                f"{self.get_server_url()}/api/profile",
                timeout=5,
                allow_redirects=False,
            )
            server_connected = response.status_code in [200, 401]
        except requests.RequestException:
            server_connected = False
        except ValueError:
            # server_url failed the HTTPS guard; treat as not connected.
            server_connected = False
        
        # Count cached protocols
        cached_protocols = 0
        if self.protocols_dir.exists():
            cached_protocols = len([
                d for d in self.protocols_dir.iterdir() 
                if d.is_dir() and not d.name.startswith('.')
            ])
        
        # Check if authenticated
        authenticated = self.auth_file.exists()
        
        return {
            "username": self.get_current_user(),
            "config_dir": str(self.config_dir),
            "server_url": self.get_server_url(),
            "server_connected": server_connected,
            "authenticated": authenticated,
            "cached_protocols": cached_protocols,
            "github_org": config["github_org"],
        }
    
    def log_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Log an audit event."""
        import datetime
        
        audit_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "event_type": event_type,
            "details": details,
        }
        
        try:
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
        except OSError:
            # Audit logging is best-effort
            pass
    
    def get_output_format(self) -> str:
        """Get the configured output format, considering environment variables."""
        if os.getenv("SECUREGENOMICS_JSON"):
            return "json"
        elif os.getenv("SECUREGENOMICS_QUIET"):
            return "quiet"
        else:
            config = self.get_config()
            return config.get("output_format", "human")
    
    def is_verbose(self) -> bool:
        """Check if verbose output is enabled."""
        return bool(os.getenv("SECUREGENOMICS_VERBOSE"))
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled."""
        return bool(os.getenv("SECUREGENOMICS_DEBUG"))
    
    def clean_cache(self) -> None:
        """Clean cached protocols and contexts."""
        import shutil
        
        # Remove protocols cache
        if self.protocols_dir.exists():
            shutil.rmtree(self.protocols_dir)
            self.protocols_dir.mkdir()
        
        # Remove crypto contexts
        if self.crypto_context_dir.exists():
            shutil.rmtree(self.crypto_context_dir)
            self.crypto_context_dir.mkdir()
        
        # Remove project data
        if self.projects_dir.exists():
            shutil.rmtree(self.projects_dir)
            self.projects_dir.mkdir()
    
    def get_protocol_cache_dir(self, protocol_name: str) -> Path:
        """Get the cache directory for a specific protocol."""
        return self.protocols_dir / protocol_name
    
    def get_crypto_context_dir(self, project_id: str) -> Path:
        """Get the crypto context directory for a specific project."""
        return self.crypto_context_dir / project_id
    
    def get_project_data_dir(self, project_id: str) -> Path:
        """Get the data directory for a specific project."""
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir
    
    @classmethod
    def find_most_recent_authenticated_user(cls) -> Optional[str]:
        """
        Find the most recently authenticated user across all directories.
        
        Returns the email of the user with the most recent valid token,
        or None if no valid tokens exist.
        """
        base_config_dir = Path.home() / ".securegenomics"
        
        if not base_config_dir.exists():
            return None
        
        valid_tokens = []
        
        for item in base_config_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                auth_file = item / "auth.json"
                if auth_file.exists():
                    try:
                        with open(auth_file, 'r') as f:
                            tokens = json.load(f)
                        
                        email = tokens.get("email")
                        expires_at = tokens.get("expires_at", 0)
                        
                        # Check if token is valid (not expired with 5 min buffer)
                        if email and expires_at > (time.time() + 300):
                            valid_tokens.append({
                                "email": email,
                                "expires_at": expires_at
                            })
                    except (json.JSONDecodeError, OSError):
                        continue
        
        if valid_tokens:
            # Return the email of the most recent token
            most_recent = max(valid_tokens, key=lambda x: x["expires_at"])
            return most_recent["email"]
        
        return None
    
    @classmethod
    def list_configured_users(cls) -> list[str]:
        """
        List all authenticated users who have configured the CLI.
        
        Returns a list of user emails who have directories under ~/.securegenomics/
        """
        base_config_dir = Path.home() / ".securegenomics"
        
        if not base_config_dir.exists():
            return []
        
        users = []
        for item in base_config_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it looks like a user directory (has auth.json with email)
                auth_file = item / 'auth.json'
                if auth_file.exists():
                    try:
                        with open(auth_file, 'r') as f:
                            tokens = json.load(f)
                        if email := tokens.get("email"):
                            users.append(email)
                    except (json.JSONDecodeError, OSError):
                        continue
        
        return sorted(users)

    def clear_base_cache(self) -> None:
        """
        Delete the entire base cache directory (~/.securegenomics/) and recreates it.
        This will remove all user configurations, auth tokens, protocols, contexts, and project data.
        """
        import shutil

        if self.base_config_dir.exists():
            try:
                shutil.rmtree(self.base_config_dir)
                console.print(f"Removed directory: {self.base_config_dir}", style="dim")
            except OSError as e:
                # Handle cases where files might be in use or other permission issues
                console.print(f"Error removing directory {self.base_config_dir}: {e}", style="red")
                raise Exception(f"Could not clear cache directory: {e}")

        # Recreate the base directory and essential subdirectories
        self._ensure_directories()
        # After clearing, there's no authenticated user
        self.clear_authenticated_user()