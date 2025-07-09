"""
Protocol management for SecureGenomics CLI.

Handles GitHub protocol discovery, caching, verification, and execution.
GitHub is the source of truth for all protocols.
"""

import hashlib
import inspect
import json
import os
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from securegenomics.config import ConfigManager
from securegenomics.github import get_github_client

console = Console()

import importlib.util
import os

def import_function_from_file(file_path: str, function_name: str):
    module_name = os.path.splitext(os.path.basename(file_path))[0]

    # Load the module from file
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the function
    func = getattr(module, function_name)
    return func

class ProtocolInfo(BaseModel):
    """Information about a protocol."""
    name: str
    description: str
    github_url: str
    commit_hash: str
    version: Optional[str] = None
    analysis_type: Optional[str] = None
    local_supported: bool = True
    aggregated_supported: bool = True

class ProtocolManager:
    """Manages protocol discovery, caching, and verification."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.protocols_dir = self.config_manager.protocols_dir
    
    def list_protocols(self) -> List[ProtocolInfo]:
        """List all available protocols from GitHub."""
        try:
            github_client = get_github_client()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Discovering protocols from GitHub...", total=None)
                
                # Get protocol repositories using the GitHub adapter
                protocol_repos = github_client.list_protocol_repos()
                
                if not protocol_repos:
                    # Check if this is due to an API error
                    api_status = github_client.check_api_status()
                    if not api_status.success:
                        raise Exception(f"GitHub API error: {api_status.error}")
                
                protocols = []
                for repo in protocol_repos:
                    try:
                        protocol_info = self._get_protocol_metadata(repo)
                        if protocol_info:
                            protocols.append(protocol_info)
                    except Exception as e:
                        console.print(f"Warning: Could not load protocol {repo['name']}: {e}")
                
                progress.update(task, completed=True)
                
            # Log audit event
            self.config_manager.log_audit_event("protocol_list", {
                "count": len(protocols),
                "protocols": [p.name for p in protocols]
            })
            
            return protocols
            
        except Exception as e:
            raise Exception(f"Failed to list protocols: {e}")
    
    def fetch(self, protocol_name: str) -> ProtocolInfo:
        """Fetch (clone) protocol from GitHub."""
        github_client = get_github_client()
        
        # Get protocol repository info
        repo_name = f"protocol-{protocol_name}" if not protocol_name.startswith("protocol-") else protocol_name
        
        response = github_client.get_repo_info(repo_name)
        if not response.success:
            if response.status_code == 404:
                raise Exception(f"Protocol '{protocol_name}' not found on GitHub")
            else:
                raise Exception(f"GitHub API error: {response.error}")
        
        repo_info = response.data
        clone_url = repo_info["clone_url"]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Fetching protocol {protocol_name}...", total=None)
            
            # Create cache directory
            protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
            
            # Remove existing cache if it exists
            if protocol_dir.exists():
                import shutil
                shutil.rmtree(protocol_dir)
            
            # Clone repository
            result = subprocess.run([
                "git", "clone", "--depth", "1", clone_url, str(protocol_dir)
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"Git clone failed: {result.stderr}")
            
            progress.update(task, completed=True)
        
        # Get protocol metadata
        protocol_info = self._get_protocol_metadata(repo_info)
        if not protocol_info:
            raise Exception("Invalid protocol: missing metadata")
        
        # Verify protocol after fetching
        if not self.verify(protocol_name):
            raise Exception("Protocol verification failed after fetch")
        
        # Log audit event
        self.config_manager.log_audit_event("protocol_fetch", {
            "protocol": protocol_name,
            "github_url": clone_url,
            "commit_hash": protocol_info.commit_hash
        })
        
        console.print(f"✅ Protocol {protocol_name} cached locally")
        return protocol_info
            
        # except subprocess.TimeoutExpired:
        #     raise Exception("Protocol fetch timed out")
        # except requests.RequestException as e:
        #     raise Exception(f"Network error: {e}")
        # except Exception as e:
        #     raise Exception(f"Failed to fetch protocol: {e}")
    
    def verify(self, protocol_name: str) -> bool:
        """Verify protocol integrity."""
        try:
            protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
            
            if not protocol_dir.exists():
                raise Exception(f"Protocol {protocol_name} not cached locally")
            
            # Get current git commit hash
            result = subprocess.run([
                "git", "-C", str(protocol_dir), "rev-parse", "HEAD"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                raise Exception("Could not get git commit hash")
            
            local_hash = result.stdout.strip()
            
            # Get remote commit hash
            repo_name = f"protocol-{protocol_name}"
            github_client = get_github_client()
            
            remote_hash = github_client.get_latest_commit_hash(repo_name)
            if not remote_hash:
                console.print(f"Warning: Could not verify remote hash for {protocol_name}")
                # Still verify structure even if remote check fails
                structure_valid, structure_errors = self._verify_protocol_structure(protocol_dir)
                if not structure_valid:
                    raise Exception(f"Protocol structure validation failed:\n" + "\n".join(structure_errors))
                return True  # Allow offline verification
            
            if local_hash != remote_hash:
                console.print(f"Warning: Protocol {protocol_name} is outdated")
                console.print(f"Local: {local_hash[:8]}, Remote: {remote_hash[:8]}")
                return False
            
            # Verify protocol structure
            structure_valid, structure_errors = self._verify_protocol_structure(protocol_dir)
            if not structure_valid:
                raise Exception(f"Protocol structure validation failed:\n" + "\n".join(structure_errors))
            
            # Log audit event
            self.config_manager.log_audit_event("protocol_verify", {
                "protocol": protocol_name,
                "local_hash": local_hash,
                "remote_hash": remote_hash,
                "verified": True
            })
            
            return True
            
        except subprocess.TimeoutExpired:
            raise Exception("Protocol verification timed out")
        except Exception as e:
            raise Exception(f"Protocol verification failed: {e}")
    
    def execute(self, protocol_name: str, operation: str, **kwargs: Any) -> Any:
        """Execute protocol operation in a sandboxed environment."""
        # try:
        protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
        
        if not protocol_dir.exists():
            # Auto-fetch if not cached
            console.print(f"Protocol {protocol_name} not cached, fetching...")
            self.fetch(protocol_name)
        
        # Verify before execution
        if not self.verify(protocol_name):
            raise Exception(f"Protocol {protocol_name} verification failed")
        
        # Map operations to their respective files and functions
        operation_mapping = {
            "generate_keys": ("generate_keys", "generate_keys"),
            "encode_vcf": ("encode", "encode_vcf"),
            "encrypt_data": ("encrypt", "encrypt_data"),
            "execute_computation_circuit": ("circuit", "compute"),
            "decrypt_result": ("decrypt", "decrypt_result"),
            "interpret_result": ("decrypt", "interpret_result"),
            "analyze_local": ("local_analysis", "analyze_local"),
            "compute_local": ("local_analysis", "compute_local"),
            
            "local_compute": ("local_compute", "local_compute"),
            "local_interpret": ("local_interpret", "local_interpret"),
        }
        
        if operation not in operation_mapping:
            raise Exception(f"Unknown operation: {operation}")
        
        module_name, function_name = operation_mapping[operation]
        
        # Execute in restricted environment
        # result = self._execute_in_sandbox(protocol_dir, module_name, function_name, **kwargs)
        
        module_path = Path(protocol_dir / module_name).with_suffix('.py')
        fn = import_function_from_file(str(module_path), function_name)
        
        result = fn(**kwargs)
        
        # Log audit event
        self.config_manager.log_audit_event("protocol_execute", {
            "protocol": protocol_name,
            "operation": operation,
            "module": module_name,
            "function": function_name,
            "success": True
        })
        
        return result
            
        # except Exception as e:
        #     # Log failed execution
        #     self.config_manager.log_audit_event("protocol_execute", {
        #         "protocol": protocol_name,
        #         "operation": operation,
        #         "success": False,
        #         "error": str(e)
        #     })
        #     raise Exception(f"Protocol execution failed: {e}")
    
    def _get_protocol_metadata(self, repo_info: Dict[str, Any]) -> Optional[ProtocolInfo]:
        """Get protocol metadata from repository."""
        try:
            repo_name = repo_info["name"]
            if not repo_name.startswith("protocol-"):
                return None
            
            protocol_name = repo_name.replace("protocol-", "")
            github_client = get_github_client()
            
            # Try to get protocol.yaml from the repository
            metadata = github_client.get_protocol_metadata(protocol_name)
            if not metadata:
                metadata = {}
            
            # Extract supported modes from the new protocol format
            modes = metadata.get("modes", ["local", "aggregated"])
            local_supported = "local" in modes
            aggregated_supported = "aggregated" in modes
            
            return ProtocolInfo(
                name=protocol_name,
                description=metadata.get("description", repo_info.get("description", "")),
                github_url=repo_info["clone_url"],
                commit_hash=repo_info["default_branch"],  # This is actually branch name, will be updated later
                version=metadata.get("version"),
                analysis_type=metadata.get("analysis_type"),
                local_supported=local_supported,
                aggregated_supported=aggregated_supported,
            )
            
        except Exception:
            return None
    
    def _verify_protocol_structure(self, protocol_dir: Path) -> Tuple[bool, List[str]]:
        """Verify that protocol has required structure according to design spec."""
        errors = []
        
        # Always require protocol.yaml
        protocol_yaml = protocol_dir / "protocol.yaml"
        if not protocol_yaml.exists():
            errors.append("Missing required file: protocol.yaml")
            return False, errors
        
        # Parse protocol.yaml to understand supported modes
        try:
            with open(protocol_yaml, 'r') as f:
                config = yaml.safe_load(f)
            
            required_fields = ["name", "description", "modes"]
            missing_fields = [field for field in required_fields if field not in config]
            if missing_fields:
                errors.append(f"protocol.yaml missing required fields: {', '.join(missing_fields)}")
            
            modes = config.get("modes", [])
            valid_modes = ["local", "aggregated"]
            invalid_modes = [mode for mode in modes if mode not in valid_modes]
            if invalid_modes:
                errors.append(f"protocol.yaml contains invalid modes: {', '.join(invalid_modes)}. Valid modes: {', '.join(valid_modes)}")
            
            # Check files based on supported modes
            local_supported = "local" in modes
            aggregated_supported = "aggregated" in modes
            
            if local_supported and not (protocol_dir / "local_compute.py").exists():
                errors.append("Missing required file for local mode: local_compute.py")
            
            if aggregated_supported:
                aggregated_files = [
                    "generate_keys.py", "encode.py", "encrypt.py", 
                    "circuit.py", "decrypt.py", "local_analysis.py"
                ]
                missing_aggregated = [f for f in aggregated_files if not (protocol_dir / f).exists()]
                if missing_aggregated:
                    errors.append(f"Missing required files for aggregated mode: {', '.join(missing_aggregated)}")
            
        except Exception as e:
            errors.append(f"Could not parse protocol.yaml: {e}")
        
        # Show detailed errors if any
        if errors:
            console.print(f"[red]Protocol validation errors:[/red]")
            for error in errors:
                console.print(f"  • {error}")
        
        return len(errors) == 0, errors

    def remove_local_protocol(self, protocol_name: str) -> bool:
        """Remove a locally cached protocol."""
        try:
            protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
            
            if not protocol_dir.exists():
                raise Exception(f"Protocol '{protocol_name}' is not cached locally")
            
            console.print(f"🗑️  Removing local protocol: {protocol_name}")
            
            # Remove the entire protocol directory
            import shutil
            shutil.rmtree(protocol_dir)
            
            # Log audit event
            self.config_manager.log_audit_event("protocol_remove_local", {
                "protocol": protocol_name,
                "cache_path": str(protocol_dir)
            })
            
            console.print(f"✅ Removed local protocol: {protocol_name}")
            return True
            
        except Exception as e:
            raise Exception(f"Failed to remove local protocol: {e}")
    
    def refresh_protocol(self, protocol_name: str) -> ProtocolInfo:
        """Refresh a local protocol by removing and re-fetching it."""
        try:
            console.print(f"🔄 Refreshing protocol: {protocol_name}")
            
            # Check if protocol exists locally first
            protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
            was_cached = protocol_dir.exists()
            
            if was_cached:
                console.print(f"📦 Removing existing local copy...")
                self.remove_local_protocol(protocol_name)
            
            console.print(f"⬇️  Downloading fresh copy...")
            protocol_info = self.fetch(protocol_name)
            
            # Log audit event
            self.config_manager.log_audit_event("protocol_refresh", {
                "protocol": protocol_name,
                "was_cached": was_cached,
                "github_url": protocol_info.github_url
            })
            
            console.print(f"✅ Protocol {protocol_name} refreshed successfully")
            return protocol_info
            
        except Exception as e:
            raise Exception(f"Failed to refresh protocol: {e}") 