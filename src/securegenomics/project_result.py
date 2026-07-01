"""Result retrieval and processing for SecureGenomics projects."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests
from rich.console import Console

from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager
from securegenomics.crypto import FHEManager
from securegenomics.protocol import ProtocolManager

console = Console()


@dataclass(frozen=True)
class ProjectResultContext:
    project_id: str
    protocol_name: str
    job_id: Optional[str] = None


class ProjectResultProcessor:
    """Fetch, decrypt, interpret, persist, and audit project results."""

    def __init__(
        self,
        *,
        server_url: str,
        auth_manager: AuthManager,
        config_manager: ConfigManager,
        fhe_manager: FHEManager,
        protocol_manager: ProtocolManager,
        project_info_loader: Callable[[str], Dict[str, Any]],
        job_status_loader: Callable[[str], Dict[str, Any]],
        encrypted_result_saver: Callable[..., Path],
        decrypted_result_saver: Callable[..., Path],
        interpreted_result_saver: Callable[..., Path],
        safe_print: Callable[..., None],
    ) -> None:
        self.server_url = server_url
        self.auth_manager = auth_manager
        self.config_manager = config_manager
        self.fhe_manager = fhe_manager
        self.protocol_manager = protocol_manager
        self.project_info_loader = project_info_loader
        self.job_status_loader = job_status_loader
        self.encrypted_result_saver = encrypted_result_saver
        self.decrypted_result_saver = decrypted_result_saver
        self.interpreted_result_saver = interpreted_result_saver
        self.safe_print = safe_print

    def get_result(self, project_id: str) -> Dict[str, Any]:
        """Get results for a completed project using protocol decrypt functions."""
        try:
            response = self._fetch_result_response(project_id)
            return self._dispatch_response_shape(project_id, response)
        except requests.RequestException as e:
            console.print(f"❌ Network error occurred: {str(e)}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            error_msg = self._binary_safe_error_message(e)
            console.print(f"❌ Error getting results: {error_msg}")
            raise Exception(f"Failed to get results: {error_msg}")

    def _fetch_result_response(self, project_id: str) -> requests.Response:
        console.print(f"📡 Fetching results for project: {project_id}")
        headers = self.auth_manager._get_auth_headers()
        response = requests.get(
            f"{self.server_url}/api/result",
            params={"project_id": project_id},
            headers=headers,
            timeout=30,
            allow_redirects=False,
        )
        console.print(
            "📡 Server response: "
            f"{response.status_code}, "
            f"Content-Type: {response.headers.get('content-type', 'unknown')}"
        )
        return response

    def _dispatch_response_shape(
        self,
        project_id: str,
        response: requests.Response,
    ) -> Dict[str, Any]:
        if response.status_code != 200:
            error_msg = self.auth_manager._parse_error_response(response)
            raise Exception(error_msg)

        content_type = response.headers.get("content-type", "").lower()
        if (
            "application/octet-stream" in content_type
            or "application/binary" in content_type
        ):
            return self._handle_binary_encrypted_payload(project_id, response.content)

        return self._handle_json_response(project_id, response)

    def _handle_binary_encrypted_payload(
        self,
        project_id: str,
        encrypted_result_bytes: bytes,
    ) -> Dict[str, Any]:
        encrypted_result_bytes = self._normalize_binary_payload(encrypted_result_bytes)
        context = self._load_result_context(project_id, include_job_id=True)
        private_context_bytes = self._load_private_context(project_id)

        result_file_path = self._persist_encrypted_result(
            context,
            encrypted_result_bytes,
            announce_size=True,
            include_job_id=True,
        )
        decrypted_result = self._decrypt_payload(
            context,
            encrypted_result=encrypted_result_bytes,
            private_context_bytes=private_context_bytes,
            json_payload=False,
        )
        decrypted_file_path = self._persist_decrypted_result(
            context,
            decrypted_result,
            include_job_id=True,
        )
        interpreted_result = self._interpret_result(context, decrypted_result)

        self._attach_result_metadata(
            interpreted_result,
            context,
            encrypted_result_path=result_file_path,
            decrypted_result_path=decrypted_file_path,
            encrypted_size_bytes=len(encrypted_result_bytes),
            include_job_id=True,
        )
        self._audit_binary_result(
            context,
            encrypted_result_path=result_file_path,
            decrypted_result_path=decrypted_file_path,
            result_size_bytes=len(encrypted_result_bytes),
        )
        return interpreted_result

    def _handle_json_response(
        self,
        project_id: str,
        response: requests.Response,
    ) -> Dict[str, Any]:
        try:
            result_data = response.json()
        except json.JSONDecodeError:
            raise Exception("Server returned invalid response format (not JSON or binary)")

        if result_data.get("encrypted"):
            return self._handle_json_encrypted_payload(project_id, result_data)

        self.config_manager.log_audit_event("project_result", {
            "project_id": project_id,
            "decrypted": False,
        })
        return result_data

    def _handle_json_encrypted_payload(
        self,
        project_id: str,
        result_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = self._load_result_context(project_id, include_job_id=False)
        private_context_bytes = self._load_private_context(project_id)
        encrypted_result = self._normalize_json_encrypted_payload(result_data)

        result_file_path = self._persist_encrypted_result(context, encrypted_result)
        decrypted_result = self._decrypt_payload(
            context,
            encrypted_result=encrypted_result,
            private_context_bytes=private_context_bytes,
            json_payload=True,
        )
        decrypted_file_path = self._persist_decrypted_result(context, decrypted_result)
        interpreted_result = self._interpret_result(context, decrypted_result)

        self._attach_result_metadata(
            interpreted_result,
            context,
            encrypted_result_path=result_file_path,
            decrypted_result_path=decrypted_file_path,
            encrypted_size_bytes=len(encrypted_result),
        )

        console.print("💾 Saving interpreted result locally...")
        interpreted_file_path = self.interpreted_result_saver(
            context.project_id,
            interpreted_result,
        )
        console.print(f"📄 Interpreted result saved to: {interpreted_file_path}")

        self._audit_json_result(
            context,
            encrypted_result_path=result_file_path,
            decrypted_result_path=decrypted_file_path,
        )
        return interpreted_result

    def _normalize_binary_payload(self, encrypted_result_bytes: bytes) -> bytes:
        if len(encrypted_result_bytes) == 0:
            raise Exception("Received empty encrypted result")
        return encrypted_result_bytes

    def _normalize_json_encrypted_payload(self, result_data: Dict[str, Any]) -> Any:
        encrypted_data = result_data["data"]
        if isinstance(encrypted_data, str):
            return bytes.fromhex(encrypted_data)
        return encrypted_data

    def _load_result_context(
        self,
        project_id: str,
        *,
        include_job_id: bool,
    ) -> ProjectResultContext:
        project_info = self.project_info_loader(project_id)
        protocol_name = project_info["protocol_name"]
        job_id = self._load_job_id(project_id) if include_job_id else None
        return ProjectResultContext(
            project_id=project_id,
            protocol_name=protocol_name,
            job_id=job_id,
        )

    def _load_job_id(self, project_id: str) -> Optional[str]:
        try:
            job_status = self.job_status_loader(project_id)
            return (job_status.get("job") or {}).get("id")
        except Exception:
            return None

    def _load_private_context(self, project_id: str) -> bytes:
        context_dir = self.config_manager.get_crypto_context_dir(project_id)
        if not context_dir.exists():
            raise Exception("Local crypto context not found. Cannot decrypt results.")

        _public_context_bytes, private_context_bytes = self.fhe_manager.load_context(
            context_dir
        )
        return private_context_bytes

    def _persist_encrypted_result(
        self,
        context: ProjectResultContext,
        encrypted_result: bytes,
        *,
        announce_size: bool = False,
        include_job_id: bool = False,
    ) -> Path:
        console.print("💾 Saving encrypted result locally...")
        if include_job_id:
            result_file_path = self.encrypted_result_saver(
                context.project_id,
                encrypted_result,
                context.job_id,
            )
        else:
            result_file_path = self.encrypted_result_saver(
                context.project_id,
                encrypted_result,
            )
        console.print(f"📁 Saved to: {result_file_path}")
        if announce_size:
            console.print(f"📊 Encrypted data size: {len(encrypted_result):,} bytes")
        return result_file_path

    def _decrypt_payload(
        self,
        context: ProjectResultContext,
        *,
        encrypted_result: bytes,
        private_context_bytes: bytes,
        json_payload: bool,
    ) -> Any:
        try:
            if json_payload:
                console.print(
                    f"🔓 Decrypting JSON results using protocol: {context.protocol_name}"
                )
                decrypted_result = self.protocol_manager.execute(
                    protocol_name=context.protocol_name,
                    operation="decrypt_result",
                    encrypted_results=encrypted_result,
                    private_crypto_context=private_context_bytes,
                )
            else:
                console.print(f"🔓 Decrypting results using protocol: {context.protocol_name}")
                decrypted_result = self.protocol_manager.execute(
                    protocol_name=context.protocol_name,
                    operation="decrypt_result",
                    encrypted_result=encrypted_result,
                    private_crypto_context=private_context_bytes,
                )

            console.print("✅ Decryption completed successfully")
            console.print(f"🔍 Decrypted result type: {type(decrypted_result)}")
            if not json_payload:
                self._display_decrypted_summary(decrypted_result)
            return decrypted_result
        except Exception as e:
            raise Exception(f"Protocol decryption failed: {str(e)}")

    def _persist_decrypted_result(
        self,
        context: ProjectResultContext,
        decrypted_result: Any,
        *,
        include_job_id: bool = False,
    ) -> Optional[Path]:
        try:
            console.print("💾 Saving decrypted result locally...")
            if include_job_id:
                decrypted_file_path = self.decrypted_result_saver(
                    context.project_id,
                    decrypted_result,
                    context.job_id,
                )
            else:
                decrypted_file_path = self.decrypted_result_saver(
                    context.project_id,
                    decrypted_result,
                )
            console.print(f"📄 Decrypted result saved to: {decrypted_file_path}")
            return decrypted_file_path
        except Exception as e:
            console.print(f"⚠️  Warning: Could not save decrypted result: {str(e)}")
            return None

    def _interpret_result(
        self,
        context: ProjectResultContext,
        decrypted_result: Any,
    ) -> Dict[str, Any]:
        try:
            console.print("📊 Interpreting results...")
            interpreted_result = self.protocol_manager.execute(
                protocol_name=context.protocol_name,
                operation="interpret_result",
                result=decrypted_result,
            )
            console.print("✅ Interpretation completed successfully")
            console.print(f"🔍 Interpreted result type: {type(interpreted_result)}")
            self._display_interpreted_summary(interpreted_result)
            return interpreted_result
        except Exception as e:
            raise Exception(f"Protocol interpretation failed: {str(e)}")

    def _display_decrypted_summary(self, decrypted_result: Any) -> None:
        if isinstance(decrypted_result, str) and len(decrypted_result) > 0:
            preview = (
                decrypted_result[:100] + "..."
                if len(decrypted_result) > 100
                else decrypted_result
            )
            self.safe_print(f"🔍 Decrypted result preview: {repr(preview)}")
        elif isinstance(decrypted_result, (bytes, bytearray)):
            console.print(f"🔍 Decrypted result is binary data ({len(decrypted_result)} bytes)")
        elif isinstance(decrypted_result, (dict, list)):
            console.print(
                "🔍 Decrypted result is "
                f"{type(decrypted_result).__name__} with {len(decrypted_result)} items"
            )
        else:
            self.safe_print(
                f"🔍 Decrypted result type: {type(decrypted_result)}, "
                f"value: {repr(decrypted_result)}"
            )

    def _display_interpreted_summary(self, interpreted_result: Any) -> None:
        if isinstance(interpreted_result, dict):
            keys = list(interpreted_result.keys())[:10]
            console.print(
                f"🔍 Interpreted result has {len(interpreted_result)} keys: {keys}"
            )
        elif isinstance(interpreted_result, list):
            console.print(
                f"🔍 Interpreted result is a list with {len(interpreted_result)} items"
            )
        elif isinstance(interpreted_result, str):
            preview = (
                interpreted_result[:200] + "..."
                if len(interpreted_result) > 200
                else interpreted_result
            )
            self.safe_print(f"🔍 Interpreted result preview: {repr(preview)}")
        elif isinstance(interpreted_result, (bytes, bytearray)):
            console.print(
                "🔍 WARNING: Interpreted result is binary data "
                f"({len(interpreted_result)} bytes) - this might cause display issues"
            )
        else:
            self.safe_print(f"🔍 Interpreted result: {repr(interpreted_result)}")

    def _attach_result_metadata(
        self,
        interpreted_result: Any,
        context: ProjectResultContext,
        *,
        encrypted_result_path: Path,
        decrypted_result_path: Optional[Path],
        encrypted_size_bytes: int,
        include_job_id: bool = False,
    ) -> None:
        if not isinstance(interpreted_result, dict):
            return

        metadata = {
            "encrypted_result_saved_to": str(encrypted_result_path),
            "decrypted_result_saved_to": str(decrypted_result_path),
            "encrypted_size_bytes": encrypted_size_bytes,
            "project_id": context.project_id,
            "protocol_name": context.protocol_name,
        }
        if include_job_id:
            metadata["job_id"] = context.job_id
        interpreted_result["_metadata"] = metadata

    def _audit_binary_result(
        self,
        context: ProjectResultContext,
        *,
        encrypted_result_path: Path,
        decrypted_result_path: Optional[Path],
        result_size_bytes: int,
    ) -> None:
        self.config_manager.log_audit_event("project_result", {
            "project_id": context.project_id,
            "protocol_name": context.protocol_name,
            "decrypted": True,
            "result_size_bytes": result_size_bytes,
            "encrypted_saved_to": str(encrypted_result_path),
            "decrypted_saved_to": str(decrypted_result_path),
            "job_id": context.job_id,
        })

    def _audit_json_result(
        self,
        context: ProjectResultContext,
        *,
        encrypted_result_path: Path,
        decrypted_result_path: Optional[Path],
    ) -> None:
        self.config_manager.log_audit_event("project_result", {
            "project_id": context.project_id,
            "protocol_name": context.protocol_name,
            "decrypted": True,
            "saved_to": str(encrypted_result_path),
            "decrypted_saved_to": str(decrypted_result_path),
        })

    def _binary_safe_error_message(self, error: Exception) -> str:
        if isinstance(error.args, tuple) and len(error.args) > 0:
            for arg in error.args:
                if isinstance(arg, (bytes, bytearray)):
                    return f"Binary data error ({len(arg)} bytes)"
        return str(error)
