"""The bridge between the desktop UI and the SecureGenomics CLI engine.

Every function here builds a *fresh* CLI manager (``AuthManager``,
``ProjectManager``, …) and calls exactly the method the corresponding
``secgen`` command calls — this mirrors the CLI's own ``_build_manager`` pattern
(one manager per command) and guarantees the desktop can never drift from the
CLI's behaviour or its security guarantees. In particular:

* The FHE keypair is generated locally by ``CryptoContextManager`` and only the
  **public** context is uploaded — the secret key never leaves this machine.
* Uploads carry ciphertext + ``encryption_stats`` only; plaintext VCF and
  decrypted results stay local. The bridge adds no network paths of its own.

Rich console output printed by the managers is captured and returned to the UI
so the desktop literally shows what the CLI would have printed.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ``run.py`` / ``server.py`` put the CLI's ``src/`` on sys.path before importing
# this module, so these imports resolve to the real engine.
from securegenomics import __version__ as cli_version
from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager
from securegenomics.crypto import FHEManager
from securegenomics.crypto_context import CryptoContextManager
from securegenomics.data import DataManager
from securegenomics.local import LocalAnalyzer
from securegenomics.project import ProjectManager
from securegenomics.protocol import ProtocolManager

from .jobs import Job


class BridgeError(Exception):
    """A user-facing error to surface in the UI (HTTP 400)."""


@contextlib.contextmanager
def _capture():
    """Capture whatever the CLI managers print to stdout/stderr."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def _build(manager_cls):
    """Instantiate a manager, translating the insecure-config error like the CLI."""
    try:
        return manager_cls()
    except ValueError as exc:  # non-loopback http:// server_url, etc.
        raise BridgeError(str(exc)) from exc


def _protocol_to_dict(protocol) -> Dict[str, Any]:
    if hasattr(protocol, "model_dump"):
        return protocol.model_dump()
    return protocol.dict()


def _json_safe(value: Any) -> Any:
    """Best-effort conversion of arbitrary manager return values to JSON."""
    return json.loads(json.dumps(value, default=str))


# ---------------------------------------------------------------------------
# System / account
# ---------------------------------------------------------------------------

def bootstrap() -> Dict[str, Any]:
    """Everything the shell needs on load: connectivity + who is signed in."""
    status = _build(ConfigManager).get_system_status()
    user = None
    if status.get("authenticated"):
        try:
            user = _build(AuthManager).whoami()
        except Exception:  # noqa: BLE001
            user = None
    return {
        "cli_version": cli_version,
        "system": _json_safe(status),
        "user": user,
    }


def login(email: str, password: str) -> Dict[str, Any]:
    if not email or not password:
        raise BridgeError("Email and password are required.")
    with _capture() as buf:
        ok = _build(AuthManager).login(email, password)
    if not ok:
        raise BridgeError("Login failed.")
    return {"console": buf.getvalue(), **bootstrap()}


def register(email: str, password: str) -> Dict[str, Any]:
    if not email or not password:
        raise BridgeError("Email and password are required.")
    if len(password) < 8:
        raise BridgeError("Password must be at least 8 characters.")
    with _capture() as buf:
        ok = _build(AuthManager).register(email, password)
    if not ok:
        raise BridgeError("Registration failed.")
    return {"console": buf.getvalue(), **bootstrap()}


def logout() -> Dict[str, Any]:
    with _capture() as buf:
        _build(AuthManager).logout()
    return {"console": buf.getvalue(), **bootstrap()}


# ---------------------------------------------------------------------------
# Protocols (GitHub-backed)
# ---------------------------------------------------------------------------

def protocols_remote() -> Dict[str, Any]:
    with _capture():
        protocols = _build(ProtocolManager).list_protocols()
    return {"protocols": [_protocol_to_dict(p) for p in protocols]}


def protocols_local() -> Dict[str, Any]:
    with _capture():
        protocols = _build(ProtocolManager).list_local_protocols()
    return {"protocols": _json_safe(protocols)}


def protocol_fetch(name: str) -> Dict[str, Any]:
    if not name:
        raise BridgeError("Protocol name is required.")
    with _capture() as buf:
        info = _build(ProtocolManager).fetch(name)
    return {"protocol": _protocol_to_dict(info), "console": buf.getvalue()}


def protocol_refresh(name: str) -> Dict[str, Any]:
    with _capture() as buf:
        info = _build(ProtocolManager).refresh_protocol(name)
    return {"protocol": _protocol_to_dict(info), "console": buf.getvalue()}


def protocol_remove(name: str) -> Dict[str, Any]:
    with _capture() as buf:
        ok = _build(ProtocolManager).remove_local_protocol(name)
    return {"removed": bool(ok), "console": buf.getvalue()}


def protocol_verify(name: str) -> Dict[str, Any]:
    if not name:
        raise BridgeError("Protocol name is required.")
    with _capture() as buf:
        ok = _build(ProtocolManager).verify(name)
    return {"valid": bool(ok), "console": buf.getvalue()}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def projects_list() -> Dict[str, Any]:
    with _capture():
        projects = _build(ProjectManager).list_projects(detailed=False)
    return {"projects": _json_safe(projects)}


def project_view(project_id: str) -> Dict[str, Any]:
    with _capture():
        info = _build(ProjectManager).view(project_id)
    return {"project": _json_safe(info)}


def project_status(project_id: str) -> Dict[str, Any]:
    with _capture():
        status = _build(ProjectManager).get_job_status(project_id)
    return {"status": _json_safe(status)}


def project_logs(project_id: str) -> Dict[str, Any]:
    with _capture():
        try:
            logs = _build(ProjectManager).get_project_job_logs(project_id)
        except Exception as exc:  # noqa: BLE001 — "no jobs yet" is normal
            return {"logs": None, "message": str(exc)}
    return {"logs": _json_safe(logs)}


def project_run(project_id: str) -> Dict[str, Any]:
    with _capture() as buf:
        job_id = _build(ProjectManager).run(project_id)
    return {"job_id": job_id, "console": buf.getvalue()}


def project_add_member(project_id: str, email: str) -> Dict[str, Any]:
    if not email:
        raise BridgeError("Member email is required.")
    with _capture() as buf:
        member = _build(ProjectManager).add_member(project_id, email)
    return {"member": _json_safe(member), "console": buf.getvalue()}


def project_delete(project_id: str) -> Dict[str, Any]:
    with _capture() as buf:
        ok = _build(ProjectManager).delete(project_id)
    if not ok:
        raise BridgeError("Failed to delete project.")
    return {"deleted": True, "console": buf.getvalue()}


def project_saved_results(project_id: str) -> Dict[str, Any]:
    results = _build(ProjectManager).list_saved_results(project_id)
    return {"results": _json_safe(results)}


# ---------------------------------------------------------------------------
# Background-job targets (executed on a worker thread)
# ---------------------------------------------------------------------------

def create_project_job(protocol_name: str):
    """Return a job target: create project, then generate & upload crypto context."""
    if not protocol_name:
        raise BridgeError("Protocol name is required.")

    def target(job: Job):
        job.set_steps(["Create project", "Generate & upload crypto context"])

        job.mark("Create project", "running")
        with _capture() as buf:
            project_id = _build(ProjectManager).create(protocol_name)
        job.log(buf.getvalue())
        job.mark("Create project", "done")

        job.mark("Generate & upload crypto context", "running")
        with _capture() as buf:
            _build(CryptoContextManager).generate_upload_crypto_context(project_id)
        job.log(buf.getvalue())
        job.mark("Generate & upload crypto context", "done")

        return {"project_id": project_id, "protocol_name": protocol_name}

    return target


def contribute_data_job(project_id: str, vcf_path: str):
    """Return a job target running encode → encrypt → upload as three tracked steps."""
    path = Path(vcf_path).expanduser()
    if not path.exists() or not path.is_file():
        raise BridgeError(f"VCF file not found: {vcf_path}")

    def target(job: Job):
        job.set_steps(["Encode", "Encrypt", "Upload"])
        manager = _build(DataManager)

        job.mark("Encode", "running")
        with _capture() as buf:
            encoded_path = manager.encode_vcf(project_id, path, None)
        job.log(buf.getvalue())
        job.mark("Encode", "done")

        job.mark("Encrypt", "running")
        with _capture() as buf:
            encrypted_path, stats = manager.encrypt_vcf(project_id, encoded_path, None)
        job.log(buf.getvalue())
        job.mark("Encrypt", "done")

        job.mark("Upload", "running")
        with _capture() as buf:
            manager.upload_data(project_id, encrypted_path, stats)
        job.log(buf.getvalue())
        job.mark("Upload", "done")

        stats_dict = stats.to_dict() if hasattr(stats, "to_dict") else None
        return {
            "encoded_path": str(encoded_path),
            "encrypted_path": str(encrypted_path),
            "encryption_stats": _json_safe(stats_dict) if stats_dict else None,
        }

    return target


def result_job(project_id: str):
    """Return a job target that downloads and locally decrypts the result."""

    def target(job: Job):
        job.set_steps(["Download & decrypt result"])
        job.mark("Download & decrypt result", "running")
        with _capture() as buf:
            result = _build(ProjectManager).get_result(project_id)
        job.log(buf.getvalue())
        job.mark("Download & decrypt result", "done")
        return _json_safe(result)

    return target


def local_analyze_job(protocol_name: str, vcf_path: str):
    """Return a job target for a fully offline local analysis."""
    if not protocol_name:
        raise BridgeError("Protocol name is required.")
    path = Path(vcf_path).expanduser()
    if not path.exists() or not path.is_file():
        raise BridgeError(f"VCF file not found: {vcf_path}")

    def target(job: Job):
        job.set_steps(["Local analyze"])
        job.mark("Local analyze", "running")
        with _capture() as buf:
            _build(LocalAnalyzer).analyze(protocol_name, path)
        output = buf.getvalue()
        job.log(output)
        job.mark("Local analyze", "done")
        return {"output": output}

    return target


# ---------------------------------------------------------------------------
# Crypto context (the FHE keypair — secret key stays local)
# ---------------------------------------------------------------------------

def crypto_context_status(project_id: str) -> Dict[str, Any]:
    manager = _build(CryptoContextManager)
    return {
        "has_local": bool(manager.has_local_crypto_context(project_id)),
        "has_server": bool(manager.has_server_crypto_context(project_id)),
    }


def crypto_context_delete(project_id: str, scope: str) -> Dict[str, Any]:
    if scope not in ("local", "server"):
        raise BridgeError("scope must be 'local' or 'server'.")
    manager = _build(CryptoContextManager)
    with _capture() as buf:
        if scope == "local":
            if not manager.has_local_crypto_context(project_id):
                raise BridgeError("No local crypto context to delete.")
            ok = manager.delete_local_crypto_context(project_id)
        else:
            if not manager.has_server_crypto_context(project_id):
                raise BridgeError("No server crypto context to delete.")
            ok = manager.delete_server_crypto_context(project_id)
    if not ok:
        raise BridgeError(f"Failed to delete {scope} crypto context.")
    return {"deleted": True, "console": buf.getvalue(), **crypto_context_status(project_id)}


def crypto_generate_job(project_id: str):
    def target(job: Job):
        job.set_steps(["Generate keypair (local)"])
        manager = _build(CryptoContextManager)
        if manager.has_server_crypto_context(project_id):
            raise BridgeError("Server already has a public context for this project.")
        if manager.has_local_crypto_context(project_id):
            raise BridgeError("A local crypto context already exists for this project.")
        job.mark("Generate keypair (local)", "running")
        with _capture() as buf:
            manager.generate_crypto_context(project_id)
        job.log(buf.getvalue())
        job.mark("Generate keypair (local)", "done")
        return crypto_context_status(project_id)

    return target


def crypto_upload_job(project_id: str):
    def target(job: Job):
        job.set_steps(["Upload public context"])
        manager = _build(CryptoContextManager)
        if manager.has_server_crypto_context(project_id):
            raise BridgeError("Server already has a public context for this project.")
        if not manager.has_local_crypto_context(project_id):
            raise BridgeError("No local crypto context to upload — generate one first.")
        job.mark("Upload public context", "running")
        with _capture() as buf:
            manager.upload_crypto_context(project_id)
        job.log(buf.getvalue())
        job.mark("Upload public context", "done")
        return crypto_context_status(project_id)

    return target


def crypto_generate_upload_job(project_id: str):
    def target(job: Job):
        job.set_steps(["Generate keypair (local)", "Upload public context"])
        manager = _build(CryptoContextManager)
        job.mark("Generate keypair (local)", "running")
        with _capture() as buf:
            manager.generate_upload_crypto_context(project_id)
        job.log(buf.getvalue())
        job.mark("Generate keypair (local)", "done")
        job.mark("Upload public context", "done")
        return crypto_context_status(project_id)

    return target


def crypto_download_job(project_id: str):
    def target(job: Job):
        job.set_steps(["Download public context"])
        job.mark("Download public context", "running")
        with _capture() as buf:
            _build(FHEManager).download_public_context(project_id)
        job.log(buf.getvalue())
        job.mark("Download public context", "done")
        return {"downloaded": True}

    return target


# ---------------------------------------------------------------------------
# Granular data pipeline (encode / encrypt / upload, run individually)
# ---------------------------------------------------------------------------

def data_encode_job(project_id: str, vcf_path: str):
    path = Path(vcf_path).expanduser()
    if not path.exists() or not path.is_file():
        raise BridgeError(f"VCF file not found: {vcf_path}")

    def target(job: Job):
        job.set_steps(["Encode"])
        job.mark("Encode", "running")
        with _capture() as buf:
            encoded_path = _build(DataManager).encode_vcf(project_id, path, None)
        job.log(buf.getvalue())
        job.mark("Encode", "done")
        return {"encoded_path": str(encoded_path)}

    return target


def data_encrypt_job(project_id: str, encoded_path: str):
    path = Path(encoded_path).expanduser()
    if not path.exists() or not path.is_file():
        raise BridgeError(f"Encoded file not found: {encoded_path}")

    def target(job: Job):
        job.set_steps(["Encrypt"])
        job.mark("Encrypt", "running")
        with _capture() as buf:
            encrypted_path, stats = _build(DataManager).encrypt_vcf(project_id, path, None)
        job.log(buf.getvalue())
        job.mark("Encrypt", "done")
        stats_dict = stats.to_dict() if hasattr(stats, "to_dict") else None
        return {"encrypted_path": str(encrypted_path), "encryption_stats": _json_safe(stats_dict) if stats_dict else None}

    return target


def data_upload_job(project_id: str, encrypted_path: str):
    path = Path(encrypted_path).expanduser()
    if not path.exists() or not path.is_file():
        raise BridgeError(f"Encrypted file not found: {encrypted_path}")

    def target(job: Job):
        job.set_steps(["Upload"])
        job.mark("Upload", "running")
        with _capture() as buf:
            _build(DataManager).upload_data(project_id, path)
        job.log(buf.getvalue())
        job.mark("Upload", "done")
        return {"uploaded": True}

    return target


# ---------------------------------------------------------------------------
# System / account
# ---------------------------------------------------------------------------

def system_status() -> Dict[str, Any]:
    return {"system": _json_safe(_build(ConfigManager).get_system_status())}


def system_clear_cache() -> Dict[str, Any]:
    with _capture() as buf:
        _build(ConfigManager).clear_base_cache()
    return {"cleared": True, "console": buf.getvalue()}


def account_delete_profile() -> Dict[str, Any]:
    with _capture() as buf:
        ok = _build(AuthManager).delete_profile()
    return {"deleted": bool(ok), "console": buf.getvalue()}
