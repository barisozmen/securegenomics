"""
Data processing management for SecureGenomics CLI.

Handles VCF file encoding, encryption, and upload operations for secure
genomic data processing.
"""

import json
import sys
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
from securegenomics.file_codec import load_file_smart, save_file_smart, write_encrypted_data
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

@dataclass(frozen=True)
class ProjectCryptoContext:
    """Project protocol/context details needed for data encryption."""
    protocol_name: str
    has_context: bool

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
    
    def _get_project_info(self, project_id: str) -> Dict[str, Any]:
        """Get project information from server."""
        try:
            response = self._make_api_request(
                "GET",
                f"/api/projects/{project_id}"
            )

            if response.status_code == 200:
                # GET /api/projects/:id nests the record under "project".
                body = response.json()
                return body.get("project", body)
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
        """Get minimal project protocol information (accessible to contributors).

        The /protocol endpoint returns a FLAT body ({project_id, protocol_name,
        has_context, ...}) — do NOT unwrap "project" here.
        """
        try:
            response = self._make_api_request(
                "GET",
                f"/api/projects/{project_id}/protocol"
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

    def _resolve_project_crypto_context(self, project_id: str) -> ProjectCryptoContext:
        """Resolve protocol and crypto-context availability for owners or contributors."""
        try:
            project_info = self._get_project_info(project_id)
            return ProjectCryptoContext(
                protocol_name=project_info["protocol_name"],
                has_context=project_info.get("has_context") or bool(project_info.get("public_context")),
            )
        except Exception:
            protocol_info = self._get_project_protocol_info(project_id)
            return ProjectCryptoContext(
                protocol_name=protocol_info["protocol_name"],
                has_context=protocol_info.get("has_context", False),
            )

    def _ensure_project_has_crypto_context(self, context: ProjectCryptoContext) -> None:
        """Raise the historical missing-context message when no public context exists."""
        if not context.has_context:
            raise Exception("Project has no crypto context. The project owner needs to generate and upload context first with 'securegenomics crypto_context generate_upload'.")

    def _get_encrypted_output_path(self, project_id: str, encoded_path: Path, output_dir: Optional[Path]) -> Path:
        """Build the encrypted file path while preserving the existing naming rules."""
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{encoded_path.stem}.encrypted"

        project_data_dir = self.config_manager.get_project_data_dir(project_id)
        if encoded_path.name.endswith('.encoded'):
            base_name = encoded_path.name[:-8]  # Remove .encoded
        else:
            base_name = encoded_path.stem
        return project_data_dir / f"{base_name}.encrypted"

    def _load_public_crypto_context(self, project_id: str) -> bytes:
        """Load the local public crypto context, downloading it when missing."""
        context_dir = self.config_manager.get_crypto_context_dir(project_id)
        if not context_dir.exists():
            self.fhe_manager.download_public_context(project_id)

        public_context_bytes, _private_context_bytes = self.fhe_manager.load_context(context_dir)
        return public_context_bytes

    def _encrypt_encoded_data(self, protocol_name: str, encoded_data: Any, public_context_bytes: bytes) -> Any:
        """Run the protocol-specific encryption operation."""
        return self.protocol_manager.execute(
            protocol_name=protocol_name,
            operation="encrypt_data",
            encoded_data=encoded_data,
            public_crypto_context=public_context_bytes
        )

    def _build_encryption_stats(
        self,
        *,
        operation_start: float,
        context_duration: float,
        data_load_duration: float,
        encryption_duration: float,
        save_duration: float,
        input_size: int,
        output_size: int,
        peak_memory: float,
        cpu_percent: float,
        protocol_name: str,
    ) -> EncryptionStats:
        """Create the encryption statistics object from measured values."""
        total_duration = time.time() - operation_start
        compression_ratio = output_size / input_size if input_size > 0 else 1.0

        return EncryptionStats(
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

    def _build_upload_payload(
        self,
        project_id: str,
        encrypted_path: Path,
        encrypted_bytes: bytes,
        encryption_stats: Optional[EncryptionStats],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Build multipart upload files and form data."""
        files = {
            "file": (encrypted_path.name, encrypted_bytes, "application/octet-stream")
        }
        data = {
            "project_id": project_id,
            "filename": encrypted_path.name
        }

        if encryption_stats:
            data["encryption_stats"] = json.dumps(encryption_stats.to_dict())

        return files, data

    def _post_upload(self, files: Dict[str, Any], data: Dict[str, Any]) -> requests.Response:
        """Send the encrypted file upload request."""
        return self._make_api_request(
            "POST",
            "/api/upload",
            files=files,
            data=data,
            timeout=300,
        )

    def _handle_upload_response(self, response: requests.Response, encrypted_path: Path) -> None:
        """Print success details or raise the same upload exceptions as before."""
        if response.status_code == 200 or response.status_code == 201:
            self._print_upload_success(response, encrypted_path)
        elif response.status_code == 409:
            self._handle_upload_conflict(response, encrypted_path)
        else:
            self._handle_upload_failure(response)

    def _print_upload_success(self, response: requests.Response, encrypted_path: Path) -> None:
        """Print successful upload details."""
        try:
            response_data = response.json()
            server_filename = response_data.get('server_filename', encrypted_path.name)
            console.print(f"✅ Encrypted data uploaded successfully")
            console.print(f"📄 Server filename: [cyan]{server_filename}[/cyan]")
        except:
            console.print(f"✅ Encrypted data uploaded successfully")

    def _handle_upload_conflict(self, response: requests.Response, encrypted_path: Path) -> None:
        """Handle server conflict responses, including duplicate filenames."""
        code = self.auth_manager._parse_error_code(response)
        if code == "duplicate_filename":
            self._raise_duplicate_filename(encrypted_path)

        error_msg = self.auth_manager._parse_error_response(response)
        raise Exception(f"Server conflict: {error_msg}")

    def _raise_duplicate_filename(self, encrypted_path: Path) -> None:
        """Print duplicate filename guidance and raise the historical error."""
        console.print(f"[red]❌ Duplicate filename error:[/red]")
        console.print(f"[red]A file named '{encrypted_path.name}' has already been uploaded[/red]")
        console.print(f"[yellow]💡 Suggestions:[/yellow]")
        console.print(f"   • Rename your file before encrypting")
        console.print(f"   • Add a timestamp or unique identifier to the filename")
        console.print(f"   • Use a different filename that hasn't been uploaded yet")
        raise Exception(f"Duplicate filename '{encrypted_path.name}' - file already exists on server")

    def _handle_upload_failure(self, response: requests.Response) -> None:
        """Print and raise non-conflict upload failures."""
        error_msg = self.auth_manager._parse_error_response(response)
        console.print(f"[red]❌ Server response (HTTP {response.status_code}):[/red]")
        console.print(f"[red]{error_msg}[/red]")
        raise Exception(f"Upload failed: {error_msg}")
    
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
                save_file_smart(encoded_path, encoded_data)
                
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
        # Initialize timing and metrics collection
        operation_start = time.time()
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        peak_memory = initial_memory
        
        try:
            if not encoded_path.exists():
                raise Exception(f"Encoded file not found: {encoded_path}")
            
            input_size = encoded_path.stat().st_size
            
            context = self._resolve_project_crypto_context(project_id)
            self._ensure_project_has_crypto_context(context)
            encrypted_path = self._get_encrypted_output_path(project_id, encoded_path, output_dir)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Loading crypto context...", total=None)
                
                context_start = time.time()
                public_context_bytes = self._load_public_crypto_context(project_id)
                context_duration = time.time() - context_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Loading encoded data...")
                
                data_load_start = time.time()
                encoded_data = load_file_smart(encoded_path)
                data_load_duration = time.time() - data_load_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Encrypting data...")
                
                encryption_start = time.time()
                encrypted_data = self._encrypt_encoded_data(context.protocol_name, encoded_data, public_context_bytes)
                encryption_duration = time.time() - encryption_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, description="Saving encrypted data...")
                
                save_start = time.time()
                encrypted_bytes = write_encrypted_data(encrypted_path, encrypted_data)
                save_duration = time.time() - save_start
                peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)
                
                progress.update(task, completed=True)
            
            stats = self._build_encryption_stats(
                operation_start=operation_start,
                context_duration=context_duration,
                data_load_duration=data_load_duration,
                encryption_duration=encryption_duration,
                save_duration=save_duration,
                input_size=input_size,
                output_size=len(encrypted_bytes),
                peak_memory=peak_memory,
                cpu_percent=process.cpu_percent(),
                protocol_name=context.protocol_name,
            )
            
            console.print(f"✅ Data encrypted using protocol: [green]{context.protocol_name}[/green]")
            console.print(f"Encrypted file saved to: [cyan]{encrypted_path}[/cyan]")
            console.print(f"⚡ Encryption completed in [blue]{stats.total_duration_seconds:.2f}s[/blue] ({stats.throughput_mbps:.1f} MB/s)")
            
            # Log audit event with enhanced metrics
            self._log_audit_event("data_encrypt_vcf",
                project_id=project_id,
                protocol_name=context.protocol_name,
                encoded_file=str(encoded_path),
                encrypted_file=str(encrypted_path),
                encrypted_size=len(encrypted_bytes),
                duration_seconds=stats.total_duration_seconds,
                throughput_mbps=stats.throughput_mbps,
                compression_ratio=stats.compression_ratio
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
                
                files, data = self._build_upload_payload(
                    project_id,
                    encrypted_path,
                    encrypted_bytes,
                    encryption_stats,
                )
                
                progress.update(task, advance=20, description="Uploading to server...")
                
                response = self._post_upload(files, data)
                if response.status_code == 200 or response.status_code == 201:
                    progress.update(task, advance=60, completed=True)

                self._handle_upload_response(response, encrypted_path)
            
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
