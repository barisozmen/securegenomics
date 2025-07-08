"""
Crypto context management for SecureGenomics CLI.

Handles FHE crypto context generation, validation, and uploading operations
for secure genomic data processing.
"""

import base64
import shutil
from pathlib import Path
from typing import Dict, Any

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager
from securegenomics.crypto import FHEManager
from securegenomics.protocol import ProtocolManager

console = Console()

class CryptoContextManager:
    """Manages FHE crypto context operations (generate, validate, upload)."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.auth_manager = AuthManager()
        self.fhe_manager = FHEManager()
        self.protocol_manager = ProtocolManager()
        self.server_url = self.config_manager.get_server_url()
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated, raise exception if not."""
        if not self.auth_manager.is_authenticated():
            raise Exception("Not authenticated. Please login first.")
    
    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated API request with consistent error handling."""
        self._ensure_authenticated()
        headers = self.auth_manager._get_auth_headers()
        
        url = f"{self.server_url}{endpoint}"
        
        # Add headers to kwargs
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
    
    def _log_audit_event(self, event_type: str, **kwargs) -> None:
        """Log audit event with consistent structure."""
        self.config_manager.log_audit_event(event_type, kwargs)
    
    def _get_project_info(self, project_id: str) -> Dict[str, Any]:
        """Get project information from server."""
        try:
            response = self._make_api_request(
                "GET",
                f"/api/projects/{project_id}/"
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise Exception(f"Project '{project_id}' not found. Please check the project ID.")
            elif response.status_code == 401:
                raise Exception("Authentication failed. Please login again.")
            elif response.status_code == 403:
                raise Exception("Access denied. You don't have permission to access this project.")
            else:
                # Parse error response using the auth manager's error parser
                error_msg = self.auth_manager._parse_error_response(response)
                raise Exception(error_msg)
        except Exception as e:
            raise
    
    # ============================================================================
    # CRYPTO CONTEXT VALIDATION OPERATIONS
    # ============================================================================
    
    def has_local_crypto_context(self, project_id: str) -> bool:
        """Check if local crypto context already exists for project."""
        context_dir = self.config_manager.get_crypto_context_dir(project_id)
        return context_dir.exists() and (context_dir / "public_context.pkl").exists()
    
    def has_server_crypto_context(self, project_id: str) -> bool:
        """Check if server already has public crypto context for project."""
        try:
            project_info = self._get_project_info(project_id)
            # Check both 'public_context' and 'has_context' fields
            # has_context is a boolean field that indicates if crypto context exists
            # public_context might be the actual data (which we don't need here)
            has_context = project_info.get("has_context", False)
            public_context = project_info.get("public_context")
            
            # Return True if either field indicates a context exists
            return has_context or bool(public_context)
        except Exception:
            # If we can't get project info, assume no context for safety
            return False
    
    def validate_crypto_context_generation(self, project_id: str) -> None:
        """Validate that crypto context can be generated for project."""
        # Check if server already has public context
        if self.has_server_crypto_context(project_id):
            raise Exception(
                f"Project {project_id} already has a public crypto context on the server. "
                "Each project can only have one crypto context for security reasons."
            )
        
        # Check if local context already exists
        if self.has_local_crypto_context(project_id):
            raise Exception(
                f"Local crypto context already exists for project {project_id}. "
                "Each project can only have one crypto context for security reasons. "
                "Use 'securegenomics crypto_context upload' to upload existing context or delete local context first."
            )
    
    # ============================================================================
    # CRYPTO CONTEXT OPERATIONS
    # ============================================================================
    
    def generate_crypto_context(self, project_id: str) -> None:
        """Generate FHE crypto context for project using TenSEAL and protocol YAML parameters."""
        # try:
        # Validate that context generation is allowed
        self.validate_crypto_context_generation(project_id)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Getting project information...", total=None)
            
            # Get project info to determine protocol
            project_info = self._get_project_info(project_id)
            protocol_name = project_info["protocol_name"]
            
            progress.update(task, description="Fetching protocol if needed...")
            
            # Ensure protocol is cached locally
            try:
                self.protocol_manager.verify(protocol_name)
            except Exception:
                # Protocol not cached or outdated, fetch it
                console.print(f"[yellow]Protocol {protocol_name} not cached, fetching...[/yellow]")
                self.protocol_manager.fetch(protocol_name)
            
            progress.update(task, description="Generating FHE crypto context with TenSEAL...")
            
            # Use FHEManager to generate context using protocol YAML parameters
            public_context_bytes, private_context_bytes = self.fhe_manager.generate_keys(protocol_name=protocol_name)
            
            progress.update(task, description="Saving context locally...")
            
            # Save context locally using FHEManager first (before uploading)
            context_dir = self.config_manager.get_crypto_context_dir(project_id)
            self.fhe_manager.save_context(public_context_bytes, private_context_bytes, context_dir)
            
            progress.update(task, completed=True)
            
            console.print(f"✅ Crypto context generated for protocol: [green]{protocol_name}[/green]")
        
        # Log audit event
        self._log_audit_event("crypto_context_generate",
            project_id=project_id,
            protocol_name=protocol_name,
        )
            
        # except Exception as e:
        #     raise Exception(f"Failed to generate crypto context: {e}")
    
    def upload_crypto_context(self, project_id: str) -> None:
        """Upload already-generated public crypto context to the server."""
        try:
            # Check if server already has public context
            if self.has_server_crypto_context(project_id):
                raise Exception(
                    f"Project {project_id} already has a public crypto context on the server. "
                    "Each project can only have one crypto context for security reasons."
                )
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Loading crypto context...", total=None)
                
                # Check if local crypto context exists
                context_dir = self.config_manager.get_crypto_context_dir(project_id)
                if not context_dir.exists():
                    raise Exception("No local crypto context found. Generate context first with 'securegenomics crypto_context generate' command.")
                
                # Load crypto context using FHEManager
                public_context_bytes, _ = self.fhe_manager.load_context(context_dir)
                
                
                
                # Convert public context bytes to base64 for JSON serialization
                public_context_b64 = base64.b64encode(public_context_bytes).decode('utf-8')
                
                progress.update(task, description=f"Uploading public context to server, at URL {self.server_url}/api/projects/{project_id}/ ...")
                
                # Upload public context to server
                headers = self.auth_manager._get_auth_headers()
                response = requests.patch(
                    f"{self.server_url}/api/projects/{project_id}/",
                    json={"public_context": public_context_b64},
                    headers=headers,
                    timeout=60
                )
                
                if response.status_code == 409:
                    # Handle crypto context already exists error
                    try:
                        error_data = response.json()
                        if error_data.get('error') == 'CRYPTO_CONTEXT_ALREADY_EXISTS':
                            raise Exception(f"Public crypto context already exists on server for project {project_id}. Each project can only have one crypto context for security reasons.")
                    except:
                        pass
                    # Fallback to generic conflict error
                    raise Exception(f"Conflict: Project {project_id} already has a public crypto context on the server.")
                elif response.status_code != 200:
                    error_msg = self.auth_manager._parse_error_response(response)
                    raise Exception(f"Failed to upload public context to server: {error_msg}")
                
                progress.update(task, completed=True)
                
                console.print(f"✅ Public crypto context uploaded for protocol: [green]OK[/green]")
            
            # Log audit event
            self._log_audit_event("crypto_context_upload",
                project_id=project_id,
            )
            
        except Exception as e:
            raise Exception(f"Failed to upload public crypto context: {e}")
    
    def generate_upload_crypto_context(self, project_id: str) -> None:
        """Generate FHE crypto context for project and upload to server (combined operation)."""
        console.print(f"🔄 Starting complete crypto context pipeline for project {project_id}")
        
        # Validate that crypto context generation is allowed
        console.print(f"🔍 Validating project {project_id}...")
        
        # Check if server already has public context
        if self.has_server_crypto_context(project_id):
            raise Exception(
                f"Project {project_id} already has a public crypto context on the server. "
                "Each project can only have one crypto context for security reasons."
            )
        
        # Check if local context already exists
        if self.has_local_crypto_context(project_id):
            raise Exception(
                f"Local crypto context already exists for project {project_id}. "
                "Each project can only have one crypto context for security reasons. "
                f"Use 'securegenomics crypto_context upload {project_id}' to upload existing context "
                "or delete the local context first if you want to regenerate."
            )
        
        console.print("✅ Validation passed - generating new crypto context", style="green")
        
        # Step 1: Generate crypto context
        console.print("\n🔐 Step 1/2: Generating crypto context...")
        self.generate_crypto_context(project_id)
        console.print(f"✅ Generated crypto context for project {project_id}", style="green")
        
        # Step 2: Upload public context to server
        console.print("\n📤 Step 2/2: Uploading public context...")
        try:
            self.upload_crypto_context(project_id)
            console.print(f"✅ Uploaded public crypto context for project {project_id}", style="green")
        except Exception as upload_error:
            # Check if it's a duplicate context error
            if "already exists on server" in str(upload_error) or "already has a public crypto context" in str(upload_error):
                console.print(f"❌ {upload_error}", style="red")
                console.print("⚠️  The crypto context was generated locally but couldn't be uploaded due to server validation.", style="yellow")
                console.print("   This indicates a race condition or validation bypass. Please contact support.", style="yellow")
                raise Exception("Context generated locally but upload failed due to server validation conflict")
            else:
                # Re-raise other upload errors
                raise
        
        console.print(f"\n✅ Complete crypto context pipeline finished successfully for project {project_id}")
        console.print(f"🔐 Project is now ready for VCF data processing")
        
        # Log audit event for complete pipeline
        self._log_audit_event("crypto_context_generate_upload",
            project_id=project_id,
            pipeline_completed=True
        )
            
        # except Exception as e:
        #     raise Exception(f"Failed to complete crypto context pipeline: {e}")
        
    def delete_local_crypto_context(self, project_id: str) -> bool:
        """Delete local crypto context for project."""
        try:
            context_dir = self.config_manager.get_crypto_context_dir(project_id)
            
            if not context_dir.exists():
                return False
            
            # Remove the entire crypto context directory
            import shutil
            shutil.rmtree(context_dir)
            
            # Log audit event
            self._log_audit_event("crypto_context_delete_local",
                project_id=project_id,
                context_dir=str(context_dir)
            )
            
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete local crypto context: {e}")
    
    def delete_server_crypto_context(self, project_id: str) -> bool:
        """Delete server crypto context for project."""
        try:
            self._ensure_authenticated()
            
            # Make DELETE request to server API
            headers = self.auth_manager._get_auth_headers()
            response = requests.delete(
                f"{self.server_url}/api/projects/{project_id}/crypto_context/",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 204:
                # Success - crypto context deleted
                self._log_audit_event("crypto_context_delete_server",
                    project_id=project_id
                )
                return True
            elif response.status_code == 404:
                raise Exception(f"Project {project_id} not found or no crypto context exists")
            elif response.status_code == 403:
                # Parse the specific error message
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", "Access denied")
                    if "not the owner" in error_msg or "owner can delete" in error_msg:
                        raise Exception(f"Access denied: Only the project owner (researcher) can delete the crypto context")
                    else:
                        raise Exception(f"Access denied: {error_msg}")
                except:
                    raise Exception("Access denied: Only the project owner (researcher) can delete the crypto context")
            else:
                error_msg = self.auth_manager._parse_error_response(response)
                raise Exception(f"Failed to delete server crypto context: {error_msg}")
                
        except Exception as e:
            if "Failed to delete server crypto context" in str(e):
                raise
            else:
                raise Exception(f"Failed to delete server crypto context: {e}")