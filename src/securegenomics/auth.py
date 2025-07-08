"""
Authentication management for SecureGenomics CLI.

Handles user authentication, JWT token management, and server communication.
Git-style auth UX: login once, persistent until explicit logout.
"""

import getpass
import json
import re
import sys
import time
from typing import Dict, Optional

import jwt
import requests
from rich.console import Console
from rich.prompt import Prompt, Confirm

from securegenomics.config import ConfigManager

console = Console()

class AuthManager:
    """Manages authentication and JWT tokens."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.auth_file = self.config_manager.auth_file
        self.server_url = self.config_manager.get_server_url()
        self.last_email_file = self.config_manager.config_dir / "last_email"
    
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
        """Login to SecureGenomics server and store JWT tokens."""
        try:
            url = f"{self.server_url}/api/login/"
            print(f"Logging in to {url} with email {email}")
            response = requests.post(
                url,
                json={"email": email, "password": password},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                tokens = {
                    "access_token": data["access"],
                    "refresh_token": data["refresh"],
                    "email": email,
                    "expires_at": self._get_token_expiry(data["access"]),
                }
                
                # Store tokens securely
                self._save_tokens(tokens)
                
                # Update config manager with authenticated user
                self.config_manager.set_authenticated_user(email)
                
                # Remember email for next time
                self._save_last_email(email)
                
                # Log audit event
                self.config_manager.log_audit_event("auth_login", {"email": email})
                
                return True
            else:
                # Parse Django Rest Framework error response
                error_msg = self._parse_error_response(response)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
        except Exception as e:
            raise Exception(f"Login failed: {e}")
    
    def register(self, email: str, password: str) -> bool:
        """Register new SecureGenomics account."""
        try:
            response = requests.post(
                f"{self.server_url}/api/register/",
                json={"email": email, "password": password},
                timeout=30
            )
            
            if response.status_code == 201:
                # Automatically login after successful registration
                return self.login(email, password)
            else:
                # Parse Django Rest Framework error response
                error_msg = self._parse_error_response(response)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
        except Exception as e:
            raise Exception(f"Registration failed: {e}")
    
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
        """Parse Django Rest Framework error response into a readable message."""
        try:
            error_data = response.json()
            
            # Check for simple detail message first
            if isinstance(error_data, dict) and "detail" in error_data:
                return error_data["detail"]
            
            # Handle Django Rest Framework validation errors
            if isinstance(error_data, dict):
                error_messages = []
                
                # Handle non_field_errors (general validation errors)
                if "non_field_errors" in error_data:
                    error_messages.extend(error_data["non_field_errors"])
                
                # Handle field-specific errors
                for field, messages in error_data.items():
                    if field != "non_field_errors":
                        if isinstance(messages, list):
                            for message in messages:
                                # For certain fields, show just the message without field name
                                if field in ["project_id", "email", "password"] and len(error_data) == 1:
                                    error_messages.append(message)
                                else:
                                    error_messages.append(f"{field}: {message}")
                        else:
                            if field in ["project_id", "email", "password"] and len(error_data) == 1:
                                error_messages.append(str(messages))
                            else:
                                error_messages.append(f"{field}: {messages}")
                
                if error_messages:
                    return "; ".join(error_messages)
            
            # Fallback if we can't parse the error
            return f"Request failed with status code: {response.status_code}"
            
        except (ValueError, TypeError):
            # Response is not valid JSON or has unexpected structure
            error_msg = f"Request failed with status code: {response.status_code}"
            
            # Try to include response text if it's reasonable length and not HTML
            if (response.text and 
                len(response.text) < 300 and 
                not response.text.strip().startswith('<')):
                error_msg += f": {response.text.strip()}"
            
            return error_msg
    
    def _save_last_email(self, email: str) -> None:
        """Save the last used email for convenience."""
        try:
            with open(self.last_email_file, 'w') as f:
                f.write(email)
            self.last_email_file.chmod(0o600)
        except OSError:
            # Non-critical, ignore errors
            pass
    
    def _load_last_email(self) -> Optional[str]:
        """Load the last used email."""
        try:
            if self.last_email_file.exists():
                with open(self.last_email_file, 'r') as f:
                    return f.read().strip()
        except OSError:
            pass
        return None
    
    def logout(self) -> None:
        """Logout by removing stored tokens."""
        # Log audit event (before clearing tokens)
        user_email = self.get_current_user_email()
        self.config_manager.log_audit_event("auth_logout", {"email": user_email})
        
        if self.auth_file.exists():
            self.auth_file.unlink()
        
        # Clear authenticated user from config manager
        self.config_manager.clear_authenticated_user()
    
    def whoami(self) -> Optional[Dict[str, str]]:
        """Get current user information."""
        tokens = self._load_tokens()
        if not tokens:
            return None
        
        # Try to get user profile from server
        try:
            headers = self._get_auth_headers()
            if not headers:
                return None
            
            response = requests.get(
                f"{self.server_url}/api/profile/",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                # Token might be expired, return cached email
                return {"email": tokens.get("email", "unknown")}
                
        except requests.RequestException:
            # Network error, return cached email
            return {"email": tokens.get("email", "unknown")}
    
    def delete_profile(self) -> bool:
        """Delete user profile and all data."""
        try:
            headers = self._get_auth_headers()
            if not headers:
                raise Exception("Not authenticated")
            
            response = requests.post(
                f"{self.server_url}/api/delete_profile/",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                # Clear local tokens after successful deletion
                self.logout()
                return True
            else:
                # Parse Django Rest Framework error response
                error_msg = self._parse_error_response(response)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")
        except Exception as e:
            raise Exception(f"Profile deletion failed: {e}")
    
    def get_token(self) -> Optional[str]:
        """Get valid access token, refreshing if necessary."""
        tokens = self._load_tokens()
        if not tokens:
            return None
        
        # Check if token is expired
        if self._is_token_expired(tokens):
            # Try to refresh token
            if self._refresh_token(tokens):
                tokens = self._load_tokens()
            else:
                return None
        
        return tokens.get("access_token")
    
    def _get_auth_headers(self) -> Optional[Dict[str, str]]:
        """Get authorization headers for API requests."""
        token = self.get_token()
        if not token:
            return None
        
        return {"Authorization": f"Bearer {token}"}
    
    def get_current_user_email(self) -> Optional[str]:
        """Get current user's email from stored tokens."""
        tokens = self._load_tokens()
        return tokens.get("email") if tokens else None
    
    def _save_tokens(self, tokens: Dict[str, str]) -> None:
        """Save tokens to auth file."""
        try:
            with open(self.auth_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            
            # Set restrictive permissions (user read/write only)
            self.auth_file.chmod(0o600)
            
        except OSError as e:
            raise Exception(f"Could not save authentication tokens: {e}")
    
    def _load_tokens(self) -> Optional[Dict[str, str]]:
        """Load tokens from auth file."""
        if not self.auth_file.exists():
            return None
        
        try:
            with open(self.auth_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    
    def _get_token_expiry(self, token: str) -> float:
        """Extract expiry time from JWT token."""
        try:
            # Decode without verification to get expiry
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded.get("exp", time.time() + 3600)  # Default to 1 hour
        except jwt.InvalidTokenError:
            return time.time() + 3600  # Default to 1 hour
    
    def _is_token_expired(self, tokens: Dict[str, str]) -> bool:
        """Check if access token is expired."""
        expires_at = tokens.get("expires_at", 0)
        # Add 5 minute buffer
        return time.time() > (expires_at - 300)
    
    def _refresh_token(self, tokens: Dict[str, str]) -> bool:
        """Refresh access token using refresh token."""
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return False
        
        try:
            response = requests.post(
                f"{self.server_url}/api/token/refresh/",
                json={"refresh": refresh_token},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                tokens["access_token"] = data["access"]
                tokens["expires_at"] = self._get_token_expiry(data["access"])
                
                # Update refresh token if provided
                if "refresh" in data:
                    tokens["refresh_token"] = data["refresh"]
                
                self._save_tokens(tokens)
                return True
            else:
                # Refresh token is invalid, clear all tokens
                self.logout()
                return False
                
        except requests.RequestException:
            return False
    
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated."""
        return self.get_token() is not None
    
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
        
        try:
            response = requests.request(method, url, **kwargs)
            return response
        except requests.RequestException as e:
            raise Exception(f"Network error: {e}")