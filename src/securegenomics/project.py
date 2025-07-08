"""
Project management for SecureGenomics CLI.

Handles multi-party aggregated computation projects, FHE context generation,
encrypted file uploads, and job management.
"""

import uuid
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

import requests
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table

from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager
from securegenomics.crypto import FHEManager
from securegenomics.protocol import ProtocolManager

console = Console()

class ProjectManager:
    """Manages aggregated analysis projects."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.auth_manager = AuthManager()
        self.fhe_manager = FHEManager()
        self.protocol_manager = ProtocolManager()
        self.server_url = self.config_manager.get_server_url()
    
    # ============================================================================
    # HELPER METHODS FOR CODE SIMPLIFICATION
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
    
    def _handle_api_response(self, response: requests.Response, success_status: int = 200, error_prefix: str = "Request failed") -> Dict[str, Any]:
        """Handle API response with consistent error parsing."""
        if response.status_code == success_status:
            return response.json() if response.content else {}
        else:
            error_msg = self.auth_manager._parse_error_response(response)
            raise Exception(f"{error_prefix}: {error_msg}")
    
    def _log_audit_event(self, event_type: str, **kwargs) -> None:
        """Log audit event with consistent structure."""
        self.config_manager.log_audit_event(event_type, kwargs)

    def _safe_print(self, *args, **kwargs) -> None:
        """Safely print data, ensuring binary data is never passed to console.print()."""
        safe_args = []
        for arg in args:
            if isinstance(arg, (bytes, bytearray)):
                # Convert binary data to a safe representation
                safe_args.append(f"<binary data: {len(arg)} bytes>")
            elif isinstance(arg, str):
                # Escape any Rich markup in strings that might contain binary data
                safe_args.append(arg.replace('[', '\\[').replace(']', '\\]'))
            else:
                safe_args.append(arg)
        console.print(*safe_args, **kwargs)
    
    def _load_file_smart(self, file_path: Path) -> Any:
        """Smart file loading that handles JSON, text, and binary formats."""
        try:
            # Try to load as JSON first
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                # Try as text
                with open(file_path, 'r') as f:
                    return f.read()
            except UnicodeDecodeError:
                # Load as binary
                with open(file_path, 'rb') as f:
                    return f.read()
    
    def _save_file_smart(self, file_path: Path, data: Any) -> None:
        """Smart file saving that handles different data types."""
        if isinstance(data, str):
            with open(file_path, 'w') as f:
                f.write(data)
        elif isinstance(data, (bytes, bytearray)):
            with open(file_path, 'wb') as f:
                f.write(data)
        else:
            # Assume it's a serializable object (dict, list, etc.)
            with open(file_path, 'w') as f:
                json.dump(data, f)

    # ============================================================================
    # PROJECT CREATION AND MANAGEMENT
    # ============================================================================
    
    def interactive_create(self) -> str:
        """Create new aggregated analysis project interactively."""
        try:
            # Check authentication first
            if not self.auth_manager.is_authenticated():
                console.print("[red]❌ Not authenticated. Please login first.[/red]")
                raise Exception("Not authenticated. Please login first.")
            
            console.print("\n[bold blue]🧬 Create New SecureGenomics Project[/bold blue]")
            console.print("This will create a new aggregated analysis project for secure multi-party computation.\n")
            
            # List available protocols
            console.print("[bold]Discovering available protocols...[/bold]")
            protocols = self.protocol_manager.list_protocols()
            
            if not protocols:
                console.print("[red]❌ No protocols available. Please check your internet connection.[/red]")
                raise Exception("No protocols available")
            
            # Display protocols in a nice table
            table = Table(title="Available Protocols")
            table.add_column("#", style="cyan", no_wrap=True)
            table.add_column("Protocol Name", style="bold green")
            table.add_column("Description", style="white")
            table.add_column("Supports", style="yellow")
            
            for i, protocol in enumerate(protocols, 1):
                supports = []
                if protocol.local_supported:
                    supports.append("Local")
                if protocol.aggregated_supported:
                    supports.append("Aggregated")
                
                table.add_row(
                    str(i),
                    protocol.name,
                    protocol.description[:60] + "..." if len(protocol.description) > 60 else protocol.description,
                    ", ".join(supports)
                )
            
            console.print(table)
            
            # Let user choose protocol
            while True:
                try:
                    choice = Prompt.ask(
                        f"\n[bold]Select a protocol[/bold] (1-{len(protocols)})",
                        console=console
                    )
                    protocol_index = int(choice) - 1
                    if 0 <= protocol_index < len(protocols):
                        selected_protocol = protocols[protocol_index]
                        break
                    else:
                        console.print(f"[red]Please enter a number between 1 and {len(protocols)}[/red]")
                except ValueError:
                    console.print("[red]Please enter a valid number[/red]")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Project creation cancelled[/yellow]")
                    raise Exception("Project creation cancelled")
            
            # Show selected protocol details
            console.print(f"\n[bold]Selected Protocol:[/bold] [green]{selected_protocol.name}[/green]")
            console.print(f"[bold]Description:[/bold] {selected_protocol.description}")
            if selected_protocol.analysis_type:
                console.print(f"[bold]Analysis Type:[/bold] {selected_protocol.analysis_type}")
            
            # Ask for optional project description
            project_description = Prompt.ask(
                "\n[bold]Project description[/bold] (optional, press Enter to skip)",
                console=console,
                default=""
            )
            
            # Confirmation
            console.print(f"\n[bold]Project Summary:[/bold]")
            console.print(f"• Protocol: [green]{selected_protocol.name}[/green]")
            if project_description:
                console.print(f"• Description: {project_description}")
            console.print(f"• GitHub URL: {selected_protocol.github_url}")
            
            if not Confirm.ask("\n[bold]Create this project?[/bold]", console=console, default=True):
                console.print("[yellow]Project creation cancelled[/yellow]")
                raise Exception("Project creation cancelled")
            
            # Create the project
            console.print("\n[bold]Creating project...[/bold]")
            project_id = self.create(selected_protocol.name)
            
            # Show next steps
            console.print("\n[bold green]✅ Project created successfully![/bold green]")
            console.print(f"[bold]Project ID:[/bold] {project_id}")
            console.print("\n[bold]Next steps:[/bold]")
            console.print(f"1. Generate crypto context: [cyan]securegenomics crypto_context generate_upload {project_id}[/cyan]")
            console.print(f"2. Upload VCF files: [cyan]securegenomics data encode_encrypt_upload {project_id} <vcf-file>[/cyan]")
            console.print(f"3. Run analysis: [cyan]securegenomics project run {project_id}[/cyan]")
            console.print(f"\n[dim]💡 For step-by-step control, use atomic commands (crypto_context generate, crypto_context upload, data encode, data encrypt, data upload)[/dim]")
            
            return project_id
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Project creation cancelled[/yellow]")
            raise Exception("Project creation cancelled")
        except Exception as e:
            if "cancelled" not in str(e).lower():
                console.print(f"\n[red]❌ Error during interactive project creation: {e}[/red]")
            raise
    
    def create(self, protocol_name: str) -> str:
        """Create new aggregated analysis project."""
        try:
            # Resolve protocol GitHub URL
            protocol_url = f"https://github.com/{self.config_manager.get_github_org()}/protocol-{protocol_name}"
            
            # Create project on server
            response = self._make_api_request(
                "POST", 
                "/api/projects/",
                json={"protocol_name": protocol_name}
            )
            
            project_data = self._handle_api_response(response, 201, "Failed to create project")
            project_id = project_data["project_id"]
            
            # Log audit event
            self._log_audit_event("project_create", 
                project_id=project_id,
                protocol_name=protocol_name,
                protocol_url=protocol_url
            )
            
            return project_id
                
        except Exception as e:
            raise Exception(f"Failed to create project: {e}")
    
    def list_projects(self, detailed: bool = False) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """List your projects."""
        try:
            params = {}
            if detailed:
                params['detailed'] = 'true'
            
            response = self._make_api_request(
                "GET",
                "/api/projects/",
                params=params
            )
            
            data = self._handle_api_response(response, 200, "Failed to list projects")
            
            if detailed:
                # Return the full response with count and projects
                return data
            else:
                # Return just the projects list for backward compatibility
                projects = data
                
                # Add status information for each project (only if it's a list)
                if isinstance(projects, list):
                    for project in projects:
                        project["status"] = self._get_project_status(project["id"])
                
                return projects
                
        except Exception as e:
            raise Exception(f"Failed to list projects: {e}")

    def view(self, project_id: str) -> Dict[str, Any]:
        """View detailed information for a specific project."""
        try:
            project_info = self._get_project_info(project_id)
            
            # Log audit event
            self._log_audit_event("project_view", project_id=project_id)
            
            return project_info
                
        except Exception as e:
            raise Exception(f"Failed to view project: {e}")

    def run(self, project_id: str) -> str:
        """Start computation for project."""
        try:
            response = self._make_api_request(
                "POST",
                "/api/run/",
                json={"project_id": project_id}
            )
            
            job_data = self._handle_api_response(response, 201, "Failed to start computation")
            job_id = job_data["job_id"]
            
            # Log audit event
            self._log_audit_event("project_run", 
                project_id=project_id,
                job_id=job_id
            )
            
            return job_id
                
        except Exception as e:
            raise Exception(f"Failed to start computation: {e}")
    
    def stop(self, project_id: str) -> str:
        """Stop running computation for project."""
        try:
            response = self._make_api_request(
                "POST",
                "/api/stop/",
                json={"project_id": project_id}
            )
            
            job_data = self._handle_api_response(response, 200, "Failed to stop computation")
            job_id = job_data["job_id"]
            
            # Log audit event
            self._log_audit_event("project_stop", 
                project_id=project_id,
                job_id=job_id
            )
            
            return job_id
                
        except Exception as e:
            raise Exception(f"Failed to stop computation: {e}")
    
    def get_job_status(self, project_id: str) -> Dict[str, Any]:
        """Check job status for project."""
        try:
            response = self._make_api_request(
                "GET",
                "/api/status/",
                params={"project_id": project_id}
            )
            
            return self._handle_api_response(response, 200, "Failed to get job status")
                
        except Exception as e:
            raise Exception(f"Failed to get job status: {e}")
        
    def get_job_logs(self, job_id: str) -> Dict[str, Any]:
        """Get detailed logs for a specific job."""
        try:
            response = self._make_api_request(
                "GET",
                f"/api/jobs/{job_id}/logs/"
            )
            
            return self._handle_api_response(response, 200, "Failed to get job logs")
                
        except Exception as e:
            raise Exception(f"Failed to get job logs: {e}")
    
    def get_project_job_logs(self, project_id: str) -> Dict[str, Any]:
        """Get logs for the latest job of a project."""
        try:
            # First get project info to find the latest job
            project_info = self._get_project_info(project_id)
            
            if not project_info.get('latest_job_id'):
                raise Exception(f"No jobs found for project {project_id}")
            
            latest_job_id = project_info['latest_job_id']
            return self.get_job_logs(latest_job_id)
                
        except Exception as e:
            raise Exception(f"Failed to get project job logs: {e}")
    
    
    def _get_results_dir(self, project_id: str) -> Path:
        """Get or create the results directory for a project."""
        project_dir = self.config_manager.get_project_data_dir(project_id)
        results_dir = project_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir
    
    def _generate_result_filename(self, project_id: str, job_id: Optional[str] = None, result_type: str = "encrypted") -> str:
        """Generate a filename for storing results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if job_id:
            return f"{result_type}_result_{project_id}_{job_id}_{timestamp}.{'bin' if result_type == 'encrypted' else 'json'}"
        else:
            return f"{result_type}_result_{project_id}_{timestamp}.{'bin' if result_type == 'encrypted' else 'json'}"
    
    def _save_encrypted_result(self, project_id: str, encrypted_data: bytes, job_id: Optional[str] = None) -> Path:
        """Save encrypted result to local storage and return the file path."""
        results_dir = self._get_results_dir(project_id)
        filename = self._generate_result_filename(project_id, job_id, "encrypted")
        result_file = results_dir / filename
        
        # Save the encrypted data
        with open(result_file, 'wb') as f:
            f.write(encrypted_data)
        
        # Log the save operation
        self._log_audit_event("encrypted_result_saved", 
            project_id = project_id,
            job_id = job_id,
            file_path = str(result_file),
            file_size_bytes = len(encrypted_data),
            filename = filename
        )
        
        return result_file

    def _save_decrypted_result(self, project_id: str, decrypted_data: Any, job_id: Optional[str] = None) -> Path:
        """Save decrypted result to local storage and return the file path."""
        results_dir = self._get_results_dir(project_id)
        filename = self._generate_result_filename(project_id, job_id, "decrypted")
        result_file = results_dir / filename
        
        # Save the decrypted data as JSON
        import json
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(decrypted_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Get file size for logging
        file_size = result_file.stat().st_size
        
        # Log the save operation
        self._log_audit_event("decrypted_result_saved", 
            project_id = project_id,
            job_id = job_id,
            file_path = str(result_file),
            file_size_bytes = file_size,
            filename = filename
        )
        
        return result_file

    def _save_interpreted_result(self, project_id: str, interpreted_data: dict, job_id: Optional[str] = None) -> Path:
        """Save interpreted result to local storage and return the file path."""
        results_dir = self._get_results_dir(project_id)
        filename = self._generate_result_filename(project_id, job_id, "interpreted")
        result_file = results_dir / filename
        
        # Save the interpreted data as JSON
        import json
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(interpreted_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Log the save operation
        self._log_audit_event("interpreted_result_saved", 
            project_id = project_id,
            job_id = job_id,
            file_path = str(result_file),
            file_size_bytes = result_file.stat().st_size,
            filename = filename
        )
        
        return result_file

    def get_result(self, project_id: str) -> Dict[str, Any]:
        """Get results for completed project using protocol's decrypt functions."""
        try:
            console.print(f"📡 Fetching results for project: {project_id}")
            headers = self.auth_manager._get_auth_headers()
            response = requests.get(
                f"{self.server_url}/api/result/",
                params={"project_id": project_id},
                headers=headers,
                timeout=30
            )
            console.print(f"📡 Server response: {response.status_code}, Content-Type: {response.headers.get('content-type', 'unknown')}")
            
            if response.status_code == 200:
                # Check content type to determine if we have binary or JSON data
                content_type = response.headers.get('content-type', '').lower()
                
                if 'application/octet-stream' in content_type or 'application/binary' in content_type:
                    # Handle binary encrypted result
                    encrypted_result_bytes = response.content
                    
                    if len(encrypted_result_bytes) == 0:
                        raise Exception("Received empty encrypted result")
                    
                    # Get project info to determine protocol and job info
                    project_info = self._get_project_info(project_id)
                    protocol_name = project_info["protocol_name"]
                    
                    # Get job status to get job ID for better filename
                    job_id = None
                    try:
                        job_status = self.get_job_status(project_id)
                        job_id = job_status.get("job_id")
                    except:
                        pass  # Continue without job_id if we can't get it
                    
                    # Save encrypted result locally FIRST
                    console.print(f"💾 Saving encrypted result locally...")
                    result_file_path = self._save_encrypted_result(project_id, encrypted_result_bytes, job_id)
                    console.print(f"📁 Saved to: {result_file_path}")
                    console.print(f"📊 Encrypted data size: {len(encrypted_result_bytes):,} bytes")
                    
                    # Load crypto context using FHEManager
                    context_dir = self.config_manager.get_crypto_context_dir(project_id)
                    if not context_dir.exists():
                        raise Exception("Local crypto context not found. Cannot decrypt results.")
                    
                    # Load crypto context - returns tuple (public_context_bytes, private_context_bytes)
                    public_context_bytes, private_context_bytes = self.fhe_manager.load_context(context_dir)
                    
                    console.print(f"🔓 Decrypting results using protocol: {protocol_name}")
                    
                    # Decrypt using protocol's decrypt.py with proper error handling
                    try:
                        decrypted_result = self.protocol_manager.execute(
                            protocol_name=protocol_name,
                            operation="decrypt_result",
                            encrypted_result=encrypted_result_bytes,
                            private_crypto_context=private_context_bytes
                        )
                        console.print(f"✅ Decryption completed successfully")
                        console.print(f"🔍 Decrypted result type: {type(decrypted_result)}")
                        
                        # Debug: Show first few characters of result if it's text/string
                        if isinstance(decrypted_result, str) and len(decrypted_result) > 0:
                            preview = decrypted_result[:100] + "..." if len(decrypted_result) > 100 else decrypted_result
                            # Use safe print to avoid Rich markup issues
                            self._safe_print(f"🔍 Decrypted result preview: {repr(preview)}")
                        elif isinstance(decrypted_result, (bytes, bytearray)):
                            console.print(f"🔍 Decrypted result is binary data ({len(decrypted_result)} bytes)")
                        elif isinstance(decrypted_result, (dict, list)):
                            console.print(f"🔍 Decrypted result is {type(decrypted_result).__name__} with {len(decrypted_result)} items")
                        else:
                            # For any other type, use safe print
                            self._safe_print(f"🔍 Decrypted result type: {type(decrypted_result)}, value: {repr(decrypted_result)}")
                        
                    except Exception as e:
                        raise Exception(f"Protocol decryption failed: {str(e)}")
                    
                    # Save decrypted result alongside encrypted result
                    try:
                        console.print(f"💾 Saving decrypted result locally...")
                        decrypted_file_path = self._save_decrypted_result(project_id, decrypted_result, job_id)
                        console.print(f"📄 Decrypted result saved to: {decrypted_file_path}")
                    except Exception as e:
                        console.print(f"⚠️  Warning: Could not save decrypted result: {str(e)}")
                        decrypted_file_path = None
                    
                    # Interpret results using protocol with proper error handling
                    try:
                        console.print(f"📊 Interpreting results...")
                        interpreted_result = self.protocol_manager.execute(
                            protocol_name=protocol_name,
                            operation="interpret_result",
                            result=decrypted_result
                        )
                        console.print(f"✅ Interpretation completed successfully")
                        console.print(f"🔍 Interpreted result type: {type(interpreted_result)}")
                        
                        # Debug: Show interpretation result safely
                        if isinstance(interpreted_result, dict):
                            console.print(f"🔍 Interpreted result has {len(interpreted_result)} keys: {list(interpreted_result.keys())[:10]}")
                        elif isinstance(interpreted_result, list):
                            console.print(f"🔍 Interpreted result is a list with {len(interpreted_result)} items")
                        elif isinstance(interpreted_result, str):
                            preview = interpreted_result[:200] + "..." if len(interpreted_result) > 200 else interpreted_result
                            self._safe_print(f"🔍 Interpreted result preview: {repr(preview)}")
                        elif isinstance(interpreted_result, (bytes, bytearray)):
                            console.print(f"🔍 WARNING: Interpreted result is binary data ({len(interpreted_result)} bytes) - this might cause display issues")
                        else:
                            self._safe_print(f"🔍 Interpreted result: {repr(interpreted_result)}")
                        
                    except Exception as e:
                        raise Exception(f"Protocol interpretation failed: {str(e)}")
                    
                    # Add metadata about the saved files to the result
                    if isinstance(interpreted_result, dict):
                        interpreted_result["_metadata"] = {
                            "encrypted_result_saved_to": str(result_file_path),
                            "decrypted_result_saved_to": str(decrypted_file_path),
                            "encrypted_size_bytes": len(encrypted_result_bytes),
                            "job_id": job_id,
                            "project_id": project_id,
                            "protocol_name": protocol_name
                        }
                        
                    # save interpreted result to a file

                    
                    # Log audit event
                    self.config_manager.log_audit_event("project_result", {
                        "project_id": project_id,
                        "protocol_name": protocol_name,
                        "decrypted": True,
                        "result_size_bytes": len(encrypted_result_bytes),
                        "encrypted_saved_to": str(result_file_path),
                        "decrypted_saved_to": str(decrypted_file_path),
                        "job_id": job_id
                    })
                    
                    
                    
                    return interpreted_result
                    
                else:
                    # Handle JSON response (legacy or error format)
                    try:
                        result_data = response.json()
                        
                        # If result is encrypted in JSON format, decrypt it using protocol
                        if result_data.get("encrypted"):
                            # Get project info to determine protocol
                            project_info = self._get_project_info(project_id)
                            protocol_name = project_info["protocol_name"]
                            
                            # Load crypto context using FHEManager
                            context_dir = self.config_manager.get_crypto_context_dir(project_id)
                            if not context_dir.exists():
                                raise Exception("Local crypto context not found. Cannot decrypt results.")
                            
                            # Load crypto context - returns tuple (public_context_bytes, private_context_bytes)
                            public_context_bytes, private_context_bytes = self.fhe_manager.load_context(context_dir)
                            
                            # Prepare encrypted result for protocol decryption
                            if isinstance(result_data["data"], str):
                                # Assume hex-encoded data
                                encrypted_result = bytes.fromhex(result_data["data"])
                            else:
                                encrypted_result = result_data["data"]
                            
                            # Save the encrypted result (from JSON format)
                            console.print(f"💾 Saving encrypted result locally...")
                            result_file_path = self._save_encrypted_result(project_id, encrypted_result)
                            console.print(f"📁 Saved to: {result_file_path}")
                            
                            # Decrypt using protocol's decrypt.py with proper error handling
                            try:
                                console.print(f"🔓 Decrypting JSON results using protocol: {protocol_name}")
                                decrypted_result = self.protocol_manager.execute(
                                    protocol_name=protocol_name,
                                    operation="decrypt_result",
                                    encrypted_results=encrypted_result,
                                    private_crypto_context=private_context_bytes
                                )
                                console.print(f"✅ Decryption completed successfully")
                                console.print(f"🔍 Decrypted result type: {type(decrypted_result)}")
                                
                            except Exception as e:
                                raise Exception(f"Protocol decryption failed: {str(e)}")
                            
                            # Save decrypted result alongside encrypted result
                            try:
                                console.print(f"💾 Saving decrypted result locally...")
                                decrypted_file_path = self._save_decrypted_result(project_id, decrypted_result)
                                console.print(f"📄 Decrypted result saved to: {decrypted_file_path}")
                            except Exception as e:
                                console.print(f"⚠️  Warning: Could not save decrypted result: {str(e)}")
                                decrypted_file_path = None
                            
                            # Interpret results using protocol with proper error handling
                            try:
                                console.print(f"📊 Interpreting results...")
                                interpreted_result = self.protocol_manager.execute(
                                    protocol_name=protocol_name,
                                    operation="interpret_result",
                                    result=decrypted_result
                                )
                                console.print(f"✅ Interpretation completed successfully")
                                console.print(f"🔍 Interpreted result type: {type(interpreted_result)}")
                                
                                # Debug: Show interpretation result safely
                                if isinstance(interpreted_result, dict):
                                    console.print(f"🔍 Interpreted result has {len(interpreted_result)} keys: {list(interpreted_result.keys())[:10]}")
                                elif isinstance(interpreted_result, list):
                                    console.print(f"🔍 Interpreted result is a list with {len(interpreted_result)} items")
                                elif isinstance(interpreted_result, str):
                                    preview = interpreted_result[:200] + "..." if len(interpreted_result) > 200 else interpreted_result
                                    self._safe_print(f"🔍 Interpreted result preview: {repr(preview)}")
                                elif isinstance(interpreted_result, (bytes, bytearray)):
                                    console.print(f"🔍 WARNING: Interpreted result is binary data ({len(interpreted_result)} bytes) - this might cause display issues")
                                else:
                                    self._safe_print(f"🔍 Interpreted result: {repr(interpreted_result)}")
                                
                            except Exception as e:
                                raise Exception(f"Protocol interpretation failed: {str(e)}")
                            
                            # Add metadata about the saved files to the result
                            if isinstance(interpreted_result, dict):
                                interpreted_result["_metadata"] = {
                                    "encrypted_result_saved_to": str(result_file_path),
                                    "decrypted_result_saved_to": str(decrypted_file_path),
                                    "encrypted_size_bytes": len(encrypted_result),
                                    "project_id": project_id,
                                    "protocol_name": protocol_name
                                }
                            
                            # Save interpreted result alongside encrypted result
                            console.print(f"💾 Saving interpreted result locally...")
                            interpreted_file_path = self._save_interpreted_result(project_id, interpreted_result)
                            console.print(f"📄 Interpreted result saved to: {interpreted_file_path}")
                            
                            # Log audit event
                            self.config_manager.log_audit_event("project_result", {
                                "project_id": project_id,
                                "protocol_name": protocol_name,
                                "decrypted": True,
                                "saved_to": str(result_file_path),
                                "decrypted_saved_to": str(decrypted_file_path)
                            })
                            
                            
                            
                            return interpreted_result
                        else:
                            # Log audit event for unencrypted result
                            self.config_manager.log_audit_event("project_result", {
                                "project_id": project_id,
                                "decrypted": False
                            })
                            
                            return result_data
                    except json.JSONDecodeError:
                        raise Exception("Server returned invalid response format (not JSON or binary)")
            else:
                # Try to parse error as JSON, fall back to text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", error_data.get("detail", "Failed to get results"))
                except json.JSONDecodeError:
                    error_msg = response.text or f"HTTP {response.status_code}: Failed to get results"
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            console.print(f"❌ Network error occurred: {str(e)}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            # Make sure we never accidentally print binary data in error messages
            error_msg = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 0:
                # Check if any of the exception args contain binary data
                for arg in e.args:
                    if isinstance(arg, (bytes, bytearray)):
                        error_msg = f"Binary data error ({len(arg)} bytes)"
                        break
            
            console.print(f"❌ Error getting results: {error_msg}")
            raise Exception(f"Failed to get results: {error_msg}")
    
    def _get_project_info(self, project_id: str) -> Optional[Dict[str, Any]]:
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
    
    def _get_project_status(self, project_id: str) -> str:
        """Get simple project status."""
        try:
            job_status = self.get_job_status(project_id)
            return job_status.get("status", "unknown")
        except Exception:
            return "unknown"
    
    def delete(self, project_id: str) -> bool:
        """Delete a project and all associated data."""
        try:
            response = self._make_api_request(
                "DELETE",
                f"/api/projects/{project_id}/"
            )
            
            if response.status_code == 204:
                # Clean up local crypto context if it exists
                context_dir = self.config_manager.crypto_context_dir / project_id
                if context_dir.exists():
                    shutil.rmtree(context_dir)
                
                # Log audit event
                self._log_audit_event("project_delete", project_id=project_id)
                
                return True
            elif response.status_code == 404:
                raise Exception("Project not found or you don't have permission to delete it")
            else:
                # Parse error response using the auth manager's error parser
                error_msg = self.auth_manager._parse_error_response(response)
                raise Exception(error_msg)
                
        except Exception as e:
            raise Exception(f"Failed to delete project: {e}")

    def list_saved_results(self, project_id: str) -> List[Dict[str, Any]]:
        """List all saved encrypted and decrypted results for a project."""
        results_dir = self._get_results_dir(project_id)
        saved_results = []
        
        if not results_dir.exists():
            return saved_results
        
        # Find all result files (both encrypted .bin and decrypted .json)
        for pattern in ["encrypted_result_*.bin", "decrypted_result_*.json"]:
            for result_file in results_dir.glob(pattern):
                try:
                    stat = result_file.stat()
                    result_type = "encrypted" if result_file.suffix == ".bin" else "decrypted"
                    saved_results.append({
                        "filename": result_file.name,
                        "full_path": str(result_file),
                        "size_bytes": stat.st_size,
                        "created_at": stat.st_ctime,
                        "modified_at": stat.st_mtime,
                        "type": result_type,
                    })
                except OSError:
                    continue
        
        # Sort by creation time (newest first)
        saved_results.sort(key=lambda x: x["created_at"], reverse=True)
        return saved_results
