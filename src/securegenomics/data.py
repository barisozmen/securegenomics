"""
Data processing management for SecureGenomics CLI.

Handles VCF file encoding, encryption, and upload operations for secure
genomic data processing.
"""

import json
import time
import psutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from securegenomics.api import AuthenticatedApiClient
from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager
from securegenomics.crypto import FHEManager
from securegenomics.protocol import ProtocolManager
from securegenomics.validation import validate_vcf_format

console = Console()

@dataclass
class EncryptionStats:
    """Elegant encapsulation of encryption operation metrics."""
    # Timing metrics
    total_duration_seconds: float
    context_load_duration_seconds: float
    data_load_duration_seconds: float
    encryption_duration_seconds: float
    save_duration_seconds: float
    
    # Data metrics
    input_size_bytes: int
    output_size_bytes: int
    compression_ratio: float
    
    # System metrics
    peak_memory_mb: float
    cpu_percent: float
    
    # Metadata
    protocol_name: str
    timestamp: str
    python_version: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @property
    def throughput_mbps(self) -> float:
        """Calculate encryption throughput in MB/s."""
        if self.encryption_duration_seconds > 0:
            return (self.input_size_bytes / 1024 / 1024) / self.encryption_duration_seconds
        return 0.0

class DataManager:
    """Manages VCF data processing operations (encode, encrypt, upload)."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.auth_manager = AuthManager()
        self.fhe_manager = FHEManager()
        self.protocol_manager = ProtocolManager()
        self.server_url = self.config_manager.get_server_url()
        self.api_client = AuthenticatedApiClient(self.auth_manager, self.config_manager)
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated, raise exception if not."""
        self.api_client._ensure_authenticated()
    
    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated API request with consistent error handling."""
        return self.api_client.request(method, endpoint, **kwargs)
    
    def _log_audit_event(self, event_type: str, **kwargs) -> None:
        """Log audit event with consistent structure."""
        self.config_manager.log_audit_event(event_type, kwargs)
    
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

    def _get_project_protocol_info(self, project_id: str) -> Dict[str, Any]:
        """Get minimal project protocol information (accessible to contributors)."""
        try:
            response = self._make_api_request(
                "GET",
                f"/api/projects/{project_id}/protocol/"
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise Exception(f"Project '{project_id}' not found. Please check the project ID.")
            elif response.status_code == 401:
                raise Exception("Authentication failed. Please login again.")
            else:
                # Parse error response using the auth manager's error parser
                error_msg = self.auth_manager._parse_error_response(response)
                raise Exception(error_msg)
        except Exception as e:
            raise
    
    def _get_protocol_name_for_project(self, project_id: str) -> str:
        """Get protocol name for project, trying full details first (for owners) then minimal info (for contributors)."""
        try:
            # Try to get full project info first (works for project owners)
            project_info = self._get_project_info(project_id)
            return project_info["protocol_name"]
        except Exception:
            # If that fails (e.g., user is not project owner), try minimal protocol info
            try:
                protocol_info = self._get_project_protocol_info(project_id)
                return protocol_info["protocol_name"]
            except Exception as e:
                raise Exception(f"Cannot access project protocol information: {e}")
    
    # ============================================================================
    # VCF DATA PROCESSING OPERATIONS
    # ============================================================================
    
    def encode_vcf(self, project_id: str, vcf_path: Path, output_dir: Optional[Path] = None) -> Path:
        """Encode VCF file using project's protocol (step 1 of 3)."""
        try:
            if not vcf_path.exists():
                raise Exception(f"VCF file not found: {vcf_path}")
            
            # Get protocol name (works for both owners and contributors)
            protocol_name = self._get_protocol_name_for_project(project_id)
            
            # Determine output path
            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                encoded_path = output_dir / f"{vcf_path.stem}.encoded"
            else:
                # Use project data directory
                project_data_dir = self.config_manager.get_project_data_dir(project_id)
                # Create a clean filename from the original VCF
                clean_name = vcf_path.name
                if clean_name.endswith('.vcf.gz'):
                    clean_name = clean_name[:-7]  # Remove .vcf.gz
                elif clean_name.endswith('.vcf'):
                    clean_name = clean_name[:-4]  # Remove .vcf
                encoded_path = project_data_dir / f"{clean_name}.encoded"
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Validating VCF file...", total=None)
                
                # Validate VCF file format
                validate_vcf_format(str(vcf_path))
                
                progress.update(task, description="Encoding VCF data...")
                
                # Encode VCF file using protocol
                encoded_data = self.protocol_manager.execute(
                    protocol_name=protocol_name,
                    operation="encode_vcf",
                    vcf_path=str(vcf_path)
                )
                
                progress.update(task, description="Saving encoded data...")
                
                # Save encoded data using smart file saving
                self._save_file_smart(encoded_path, encoded_data)
                
                progress.update(task, completed=True)
            
            console.print(f"✅ VCF encoded using protocol: [green]{protocol_name}[/green]")
            console.print(f"Encoded file saved to: [cyan]{encoded_path}[/cyan]")
            
            # Log audit event
            self._log_audit_event("data_encode_vcf",
                project_id=project_id,
                protocol_name=protocol_name,
                vcf_file=str(vcf_path),
                encoded_file=str(encoded_path),
                file_size=vcf_path.stat().st_size
            )
            
            return encoded_path
            
        except Exception as e:
            raise Exception(f"Failed to encode VCF file: {e}")
    
    def encrypt_vcf(self, project_id: str, encoded_path: Path, output_dir: Optional[Path] = None) -> tuple[Path, EncryptionStats]:
        """Encrypt encoded VCF data using project's crypto context (step 2 of 3)."""
        import sys
        
        # Initialize timing and metrics collection
        operation_start = time.time()
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        peak_memory = initial_memory
        
        try:
            if not encoded_path.exists():
                raise Exception(f"Encoded file not found: {encoded_path}")
            
            input_size = encoded_path.stat().st_size
            
            # Get protocol name and check if project has context (works for both owners and contributors)
            try:
                # Try to get full project info first (for owners)
                project_info = self._get_project_info(project_id)
                protocol_name = project_info["protocol_name"]
                has_context = project_info.get("has_context") or bool(project_info.get("public_context"))
            except Exception:
                # Fall back to minimal protocol info (for contributors)
                protocol_info = self._get_project_protocol_info(project_id)
                protocol_name = protocol_info["protocol_name"]
                has_context = protocol_info.get("has_context", False)
            
            # Check if project has public context
            if not has_context:
                raise Exception("Project has no crypto context. The project owner needs to generate and upload context first with 'securegenomics crypto_context generate_upload'.")
            
            # Determine output path
            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                encrypted_path = output_dir / f"{encoded_path.stem}.encrypted"
            else:
                # Use project data directory and smart naming
                project_data_dir = self.config_manager.get_project_data_dir(project_id)
                # Create clean name: if it ends with .encoded, replace with .encrypted
                if encoded_path.name.endswith('.encoded'):
                    base_name = encoded_path.name[:-8]  # Remove .encoded
                else:
                    base_name = encoded_path.stem
                encrypted_path = project_data_dir / f"{base_name}.encrypted"
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Loading crypto context...", total=None)
                
                # 🎯 Phase 1: Load crypto context
                context_start = time.time()
                context_dir = self.config_manager.get_crypto_context_dir(project_id)
                if not context_dir.exists():
                    # Download public context from server
                    self.fhe_manager.download_public_context(project_id)
                
                # Load crypto context - returns tuple (public_context_bytes, private_context_bytes)
                public_context_bytes, private_context_bytes = self.fhe_manager.load_context(context_dir)
                context_duration = time.time() - context_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Loading encoded data...")
                
                # 🎯 Phase 2: Load encoded data
                data_load_start = time.time()
                encoded_data = self._load_file_smart(encoded_path)
                data_load_duration = time.time() - data_load_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Encrypting data...")
                
                # 🎯 Phase 3: Core encryption operation
                encryption_start = time.time()
                encrypted_data = self.protocol_manager.execute(
                    protocol_name=protocol_name,
                    operation="encrypt_data",
                    encoded_data=encoded_data,
                    public_crypto_context=public_context_bytes
                )
                encryption_duration = time.time() - encryption_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Saving encrypted data...")
                
                # 🎯 Phase 4: Save encrypted data
                save_start = time.time()
                # Convert encrypted data to bytes for storage
                if isinstance(encrypted_data, str):
                    encrypted_bytes = encrypted_data.encode('utf-8')
                elif isinstance(encrypted_data, dict):
                    encrypted_bytes = json.dumps(encrypted_data).encode('utf-8')
                else:
                    encrypted_bytes = encrypted_data
                
                with open(encrypted_path, 'wb') as f:
                    f.write(encrypted_bytes)
                save_duration = time.time() - save_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, completed=True)
            
            # Calculate final metrics
            total_duration = time.time() - operation_start
            output_size = len(encrypted_bytes)
            compression_ratio = output_size / input_size if input_size > 0 else 1.0
            cpu_percent = process.cpu_percent()
            
            # Create elegant statistics object
            stats = EncryptionStats(
                total_duration_seconds=total_duration,
                context_load_duration_seconds=context_duration,
                data_load_duration_seconds=data_load_duration,
                encryption_duration_seconds=encryption_duration,
                save_duration_seconds=save_duration,
                input_size_bytes=input_size,
                output_size_bytes=output_size,
                compression_ratio=compression_ratio,
                peak_memory_mb=peak_memory,
                cpu_percent=cpu_percent,
                protocol_name=protocol_name,
                timestamp=datetime.now().isoformat(),
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            )
            
            console.print(f"✅ Data encrypted using protocol: [green]{protocol_name}[/green]")
            console.print(f"Encrypted file saved to: [cyan]{encrypted_path}[/cyan]")
            console.print(f"⚡ Encryption completed in [blue]{total_duration:.2f}s[/blue] ({stats.throughput_mbps:.1f} MB/s)")
            
            # Log audit event with enhanced metrics
            self._log_audit_event("data_encrypt_vcf",
                project_id=project_id,
                protocol_name=protocol_name,
                encoded_file=str(encoded_path),
                encrypted_file=str(encrypted_path),
                encrypted_size=len(encrypted_bytes),
                duration_seconds=total_duration,
                throughput_mbps=stats.throughput_mbps,
                compression_ratio=compression_ratio
            )
            
            return encrypted_path, stats
            
        except Exception as e:
            raise Exception(f"Failed to encrypt VCF data: {e}")
    
    def upload_data(self, project_id: str, encrypted_path: Path, encryption_stats: Optional[EncryptionStats] = None) -> None:
        """Upload encrypted data file to server (step 3 of 3)."""
        try:
            if not encrypted_path.exists():
                raise Exception(f"Encrypted file not found: {encrypted_path}")
            
            # Get protocol name (works for both owners and contributors)
            protocol_name = self._get_protocol_name_for_project(project_id)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                task = progress.add_task("Uploading encrypted file...", total=100)
                
                # Load encrypted data
                with open(encrypted_path, 'rb') as f:
                    encrypted_bytes = f.read()
                
                progress.update(task, advance=20)
                
                # Upload encrypted file to server
                headers = self.auth_manager._get_auth_headers()
                
                
                files = {
                    "file": (encrypted_path.name, encrypted_bytes, "application/octet-stream")
                }
                data = {
                    "project_id": project_id,
                    "filename": encrypted_path.name
                }
                
                # Include encryption statistics if available
                if encryption_stats:
                    data["encryption_stats"] = json.dumps(encryption_stats.to_dict())
                
                progress.update(task, advance=20, description="Uploading to server...")
                
                response = requests.post(
                    f"{self.server_url}/api/upload/",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=300
                )
                
                if response.status_code == 200 or response.status_code == 201:
                    progress.update(task, advance=60, completed=True)
                    
                    # Parse successful response to get filename info
                    try:
                        response_data = response.json()
                        filename = response_data.get('filename', encrypted_path.name)
                        console.print(f"✅ Encrypted data uploaded successfully")
                        console.print(f"📄 Server filename: [cyan]{filename}[/cyan]")
                    except:
                        console.print(f"✅ Encrypted data uploaded successfully")
                        
                elif response.status_code == 409:
                    # Handle duplicate filename specifically
                    try:
                        error_data = response.json()
                        if error_data.get('error') == 'DUPLICATE_FILENAME':
                            filename = error_data.get('filename', 'unknown')
                            console.print(f"[red]❌ Duplicate filename error:[/red]")
                            console.print(f"[red]A file named '{filename}' has already been uploaded[/red]")
                            console.print(f"[yellow]💡 Suggestions:[/yellow]")
                            console.print(f"   • Rename your file before encrypting")
                            console.print(f"   • Add a timestamp or unique identifier to the filename")
                            console.print(f"   • Use a different filename that hasn't been uploaded yet")
                            raise Exception(f"Duplicate filename '{filename}' - file already exists on server")
                        else:
                            error_msg = error_data.get('detail', 'Conflict error')
                            raise Exception(f"Server conflict: {error_msg}")
                    except Exception as parse_error:
                        if "Duplicate filename" in str(parse_error):
                            raise parse_error  # Re-raise our custom duplicate filename error
                        else:
                            raise Exception(f"Server conflict (HTTP 409) - unable to parse response")
                else:
                    # Try to get detailed error information
                    try:
                        error_data = response.json()
                        if 'detail' in error_data:
                            error_msg = error_data['detail']
                        elif isinstance(error_data, dict):
                            # Handle validation errors from serializer
                            error_parts = []
                            for field, errors in error_data.items():
                                if isinstance(errors, list):
                                    error_parts.append(f"{field}: {', '.join(errors)}")
                                else:
                                    error_parts.append(f"{field}: {errors}")
                            error_msg = "; ".join(error_parts)
                        else:
                            error_msg = str(error_data)
                    except:
                        error_msg = f"Upload failed (HTTP {response.status_code})"
                    
                    console.print(f"[red]❌ Server response (HTTP {response.status_code}):[/red]")
                    console.print(f"[red]{error_msg}[/red]")
                    raise Exception(f"Upload failed: {error_msg}")
            
            # Log audit event
            self._log_audit_event("data_upload_data",
                project_id=project_id,
                protocol_name=protocol_name,
                encrypted_file=str(encrypted_path),
                file_size=encrypted_path.stat().st_size
            )
            
        except Exception as e:
            raise Exception(f"Failed to upload encrypted data: {e}")
    
    def encode_encrypt_upload(self, project_id: str, vcf_path: Path, output_dir: Optional[Path] = None) -> None:
        """Complete VCF processing pipeline: encode, encrypt, and upload (combined operation)."""
        try:
            console.print(f"🔄 Starting complete VCF processing pipeline for {vcf_path.name}")
            
            # Step 1: Encode
            console.print("\n📝 Step 1/3: Encoding VCF...")
            encoded_path = self.encode_vcf(project_id, vcf_path, output_dir)
            
            # Step 2: Encrypt  
            console.print("\n🔒 Step 2/3: Encrypting encoded data...")
            encrypted_path, encryption_stats = self.encrypt_vcf(project_id, encoded_path, output_dir)
            
            # Step 3: Upload with statistics
            console.print("\n📤 Step 3/3: Uploading encrypted data...")
            self.upload_data(project_id, encrypted_path, encryption_stats)
            
            console.print(f"\n✅ Complete pipeline finished successfully for {vcf_path.name}")
            console.print(f"📁 Intermediate files:")
            console.print(f"  • Encoded: {encoded_path}")
            console.print(f"  • Encrypted: {encrypted_path}")
            
            # Log audit event for complete pipeline
            self._log_audit_event("data_encode_encrypt_upload",
                project_id=project_id,
                vcf_file=str(vcf_path),
                encoded_file=str(encoded_path),
                encrypted_file=str(encrypted_path),
                pipeline_completed=True
            )
            
        except Exception as e:
            raise Exception(f"Failed to complete VCF processing pipeline: {e}")
