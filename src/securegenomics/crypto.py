"""
FHE Cryptography management for SecureGenomics CLI.

Handles FHE context generation, VCF encryption/decryption, and key management.
Uses BFV scheme optimized for integer arithmetic on genomic data.
"""

import pickle
import gzip
import yaml
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from securegenomics.protocol import ProtocolManager

from pydantic import BaseModel
from rich.console import Console

console = Console()

class FHEManager:
    """Manages FHE encryption, decryption, and context operations."""
    
    def __init__(self) -> None:
        self.default_parameters = {
            # BFV parameters for genomic data
            "poly_modulus_degree": 8192,
            "coeff_modulus": [60, 40, 40, 60],
            "plain_modulus": 1024,
            "scale": 2**40
        }
        
        # Initialize managers for API access
        from securegenomics.auth import AuthManager
        from securegenomics.config import ConfigManager
        self.auth_manager = AuthManager()
        self.config_manager = ConfigManager()
        self.server_url = self.config_manager.get_server_url()
        self.protocol_manager = ProtocolManager()

    def generate_keys(self, protocol_name: str):
        public_context_bytes, private_context_bytes = self.protocol_manager.execute(
            protocol_name=protocol_name,
            operation="generate_keys"
        )
        return public_context_bytes, private_context_bytes
    
    # def generate_crypto_context(self, protocol_name: str) -> CryptoContext:
    #     """
    #     Generate FHE context using parameters from protocol YAML configuration.
        
    #     Args:
    #         protocol_name: Name of the protocol to load parameters for
            
    #     Returns:
    #         CryptoContext object containing the generated FHE context and keys
    #     """
    #     try:
    #         # Import config manager to get protocol directory
    #         from securegenomics.config import ConfigManager
    #         config_manager = ConfigManager()
            
    #         # Get protocol directory
    #         protocol_dir = config_manager.get_protocol_cache_dir(protocol_name)
    #         if not protocol_dir.exists():
    #             raise Exception(f"Protocol {protocol_name} not found. Please fetch it first.")
            
    #         # Load protocol YAML configuration
    #         protocol_yaml_path = protocol_dir / "protocol.yaml"
    #         if not protocol_yaml_path.exists():
    #             raise Exception(f"Protocol configuration file not found: {protocol_yaml_path}")
            
    #         with open(protocol_yaml_path, 'r') as f:
    #             protocol_config = yaml.safe_load(f)
            
    #         # Extract FHE parameters from protocol config
    #         fhe_params = protocol_config.get('fhe_params', {})
    #         if not fhe_params:
    #             console.print(f"[yellow]Warning: No FHE parameters found in protocol {protocol_name}, using defaults[/yellow]")
    #             fhe_params = self.default_parameters
            
    #         # Validate and normalize parameters
    #         poly_modulus_degree = fhe_params.get('poly_modulus_degree', self.default_parameters['poly_modulus_degree'])
    #         plain_modulus = fhe_params.get('plain_modulus', self.default_parameters['plain_modulus'])
    #         coeff_modulus = fhe_params.get('coeff_modulus_bits', fhe_params.get('coeff_modulus', self.default_parameters['coeff_modulus']))
    #         scheme = fhe_params.get('scheme', 'BFV').upper()
            
    #         console.print(f"[blue]Generating FHE context for protocol: {protocol_name}[/blue]")
    #         console.print(f"Scheme: {scheme}")
    #         console.print(f"Polynomial modulus degree: {poly_modulus_degree}")
    #         console.print(f"Plain modulus: {plain_modulus}")
    #         console.print(f"Coefficient modulus: {coeff_modulus}")
            
    #         if ts is None:
    #             # Fallback to mock implementation if TenSEAL not available
    #             console.print("[yellow]Using mock FHE context (TenSEAL not available)[/yellow]")
    #             return self._generate_mock_context_object(protocol_name, fhe_params)
            
    #         # Create TenSEAL context based on scheme
    #         if scheme == 'BFV':
    #             # For BFV, use the correct TenSEAL API
    #             context = ts.context(
    #                 ts.SCHEME_TYPE.BFV,
    #                 poly_modulus_degree,
    #                 plain_modulus
    #             )
    #             # TenSEAL automatically chooses coefficient modulus for BFV based on security
    #             console.print(f"[dim]Note: TenSEAL automatically chose coefficient modulus for security[/dim]")
                
    #         elif scheme == 'CKKS':
    #             # For CKKS, create context and set scale
    #             context = ts.context(
    #                 ts.SCHEME_TYPE.CKKS,
    #                 poly_modulus_degree
    #             )
    #             # Set global scale for CKKS
    #             scale = fhe_params.get('scale', self.default_parameters['scale'])
    #             context.global_scale = scale
    #             console.print(f"Scale: {scale}")
                
    #         else:
    #             raise Exception(f"Unsupported FHE scheme: {scheme}")
            
    #         # Generate keys
    #         context.generate_galois_keys()
    #         context.generate_relin_keys()
            
    #         # Serialize context - TenSEAL handles public/private context automatically
    #         secret_key_bytes = context.serialize()  # Full context with secret key
            
    #         # Create a copy of the context for public operations
    #         public_context_bytes = context.serialize()  # Same as secret for now - protocols can manage access
            
    #         # Store actual parameters used
    #         actual_parameters = {
    #             'scheme': scheme,
    #             'poly_modulus_degree': poly_modulus_degree,
    #             'plain_modulus': plain_modulus if scheme == 'BFV' else None,
    #             'coeff_modulus_note': 'Automatically chosen by TenSEAL for security',
    #             'scale': context.global_scale if scheme == 'CKKS' and hasattr(context, 'global_scale') else None,
    #             'security_level': self._estimate_security_level({'poly_modulus_degree': poly_modulus_degree})
    #         }
            
    #         console.print("✅ FHE context generated successfully")
            
    #         return CryptoContext(
    #             protocol_name=protocol_name,
    #             public_context_bytes=public_context_bytes,
    #             secret_key_bytes=secret_key_bytes,
    #             parameters=actual_parameters
    #         )
            
    #     except Exception as e:
    #         raise Exception(f"Failed to generate FHE context: {e}")

    
    def save_context(self, public_context_bytes: bytes, private_context_bytes: bytes, context_dir: Path) -> None:
        """Save crypto context to disk."""
        try:
            context_dir.mkdir(parents=True, exist_ok=True)

            with open(context_dir / "public_crypto_context.bin", 'wb') as f:
                f.write(public_context_bytes)
            
            with open(context_dir / "private_crypto_context.bin", 'wb') as f:
                f.write(private_context_bytes)
            
        except Exception as e:
            raise Exception(f"Failed to save crypto context: {e}")
        else:
            console.print(f"💾 Saved public and private crypto context to: {context_dir}")
    
    def load_context(self, context_dir: Path) -> Tuple[bytes, bytes]:
        """Load crypto context from disk."""
        try:
            if not context_dir.exists():
                raise Exception("Crypto context directory not found")
            
            # Load public context
            public_path = context_dir / "public_crypto_context.bin"
            if not public_path.exists():
                raise Exception("Public context file not found")
            
            with open(public_path, 'rb') as f:
                public_context_bytes = f.read()
            
            # Load (optional) private context (that includes the secret key)
            private_context_bytes = None
            private_path = context_dir / "private_crypto_context.bin"
            if private_path.exists():
                with open(private_path, 'rb') as f:
                    private_context_bytes = f.read()
            
            return public_context_bytes, private_context_bytes
            
        except Exception as e:
            raise Exception(f"Failed to load crypto context: {e}")
    
    def _protocol_name_for_project(self, project_id: str) -> str:
        """Resolve a project's protocol name via the API.

        The context download stream is opaque bytes, so the protocol name must
        come from project info. Tries the flat /protocol endpoint first
        (contributor-accessible), then the full project endpoint (owner; nested
        under "project"). Degrades to "unknown" rather than raising.
        """
        headers = self.auth_manager._get_auth_headers()
        base = self.server_url

        try:
            resp = requests.get(
                f"{base}/api/projects/{project_id}/protocol",
                headers=headers, timeout=30, allow_redirects=False,
            )
            if resp.status_code == 200:
                name = resp.json().get("protocol_name")
                if name:
                    return name
        except requests.RequestException:
            pass
        except (ValueError, TypeError):
            pass

        try:
            resp = requests.get(
                f"{base}/api/projects/{project_id}",
                headers=headers, timeout=30, allow_redirects=False,
            )
            if resp.status_code == 200:
                body = resp.json()
                project = body.get("project", body)
                name = project.get("protocol_name")
                if name:
                    return name
        except requests.RequestException:
            pass
        except (ValueError, TypeError):
            pass

        return "unknown"

    def download_public_context(self, project_id: str) -> bytes:
        """Download public context from server and save locally.
        
        Args:
            project_id: UUID of the project to download context for
            
        Returns:
            CryptoContext object with the downloaded public context
            
        Raises:
            Exception: If download fails or user not authenticated
        """
        try:
            # Check authentication
            if not self.auth_manager or not self.auth_manager.is_authenticated():
                raise Exception("Not authenticated. Please login first.")
            
            console.print(f"🔽 Downloading public crypto context for project {project_id}...")
            
            # Make API request to download context
            headers = self.auth_manager._get_auth_headers()
            url = f"{self.server_url}/api/context/download"
            params = {"project_id": project_id}
            
            # Debug logging
            if self.config_manager and self.config_manager.is_debug():
                console.print(f"[dim]DEBUG: Making request to {url}[/dim]")
                console.print(f"[dim]DEBUG: Params: {params}[/dim]")
                console.print(f"[dim]DEBUG: Headers: {list(headers.keys()) if headers else 'None'}[/dim]")
            
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=30,
                allow_redirects=False,
            )

            # Debug logging for response
            if self.config_manager and self.config_manager.is_debug():
                console.print(f"[dim]DEBUG: Response status: {response.status_code}[/dim]")
                console.print(f"[dim]DEBUG: Response headers: {dict(response.headers)}[/dim]")

            if response.status_code == 200:
                # Rails streams the public context as RAW BINARY bytes — not JSON.
                public_context_bytes = response.content
                context_size = len(public_context_bytes)

                if context_size == 0:
                    raise Exception("Received an empty public context from the server")

                # Protocol name comes from already-fetched project info, not the
                # download response (which is opaque bytes).
                protocol_name = self._protocol_name_for_project(project_id)

                console.print(f"📦 Downloaded context: {context_size} bytes for protocol {protocol_name}")

                # Save context locally for future use
                context_dir = None
                if self.config_manager:
                    try:
                        context_dir = self.config_manager.get_crypto_context_dir(project_id)
                        context_dir.mkdir(parents=True, exist_ok=True)

                        # Save public context with standard filename for load_context compatibility
                        with open(context_dir / "public_crypto_context.bin", 'wb') as f:
                            f.write(public_context_bytes)

                        # Save metadata for reference
                        metadata = {
                            "project_id": project_id,
                            "protocol_name": protocol_name,
                            "context_size": context_size,
                            "downloaded": True,
                            "source": "server"
                        }
                        metadata_path = context_dir / "crypto_context_metadata.pkl"
                        with open(metadata_path, 'wb') as f:
                            pickle.dump(metadata, f)

                        console.print(f"💾 Saved public context to: {context_dir}")
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not save context locally: {e}[/yellow]")

                console.print(f"✅ Public crypto context ({context_size} bytes) downloaded successfully to {context_dir}")
                return public_context_bytes
                
            elif response.status_code == 404:
                if "project_id" in response.text.lower():
                    raise Exception(f"Project {project_id} not found or you don't have access to it.")
                else:
                    raise Exception(f"No public context available for project {project_id}. The project owner needs to generate and upload the context first.")
            elif response.status_code == 401:
                raise Exception("Authentication failed. Please login again.")
            elif response.status_code == 403:
                raise Exception("Access denied. You don't have permission to access this project's context.")
            else:
                # Parse error response using the auth manager's error parser
                error_msg = self.auth_manager._parse_error_response(response)
                raise Exception(f"Failed to download context: {error_msg}")
                
        except requests.RequestException as e:
            raise Exception(f"Network error while downloading context: {e}")
        except Exception as e:
            # Re-raise custom exceptions as-is, wrap others
            if "Failed to download context" in str(e) or "Not authenticated" in str(e) or "Project" in str(e):
                raise
            else:
                raise Exception(f"Failed to download public context: {e}")