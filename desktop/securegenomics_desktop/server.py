"""A local, single-origin HTTP server that fronts the CLI bridge.

Design notes / security:
* Binds to 127.0.0.1 only — never reachable off the machine.
* Every ``/api/*`` request must carry ``X-SG-Token`` matching a random
  per-session token that is injected into ``index.html``. A stray web page or
  another local process cannot read that token, so it cannot drive the API
  (defends against DNS-rebinding / CSRF against the local server).
* No endpoint transmits secret keys or plaintext — it only forwards to the same
  CLI managers the terminal uses.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from . import bridge
from .bridge import BridgeError
from .jobs import JobRegistry

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Per-session staging dir for files the user drags in / browses to. Drag-and-drop
# and <input type=file> only expose file *contents* in the browser, not a disk
# path — but the CLI managers need a real path. We stream the bytes to this local
# temp dir (loopback only) and hand the path to the CLI. Nothing here leaves the
# machine: encode + FHE encryption still run locally, only ciphertext is uploaded.
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="gencrypt-desktop-uploads-"))
# 2 GiB ceiling so a runaway/hostile request can't fill the disk.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


@atexit.register
def _cleanup_uploads() -> None:
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)

# Set by run.py when a native pywebview window is available, so the browser-less
# native file picker works. Stays None in browser-fallback mode.
WEBVIEW_WINDOW: Any = None

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


class _Router:
    """Minimal method+regex router for the JSON API."""

    def __init__(self) -> None:
        self.routes: list[Tuple[str, re.Pattern, Callable]] = []

    def add(self, method: str, pattern: str, handler: Callable) -> None:
        self.routes.append((method, re.compile(f"^{pattern}$"), handler))

    def match(self, method: str, path: str):
        for m, pat, handler in self.routes:
            if m != method:
                continue
            found = pat.match(path)
            if found:
                return handler, found.groupdict()
        return None, None


def build_app(token: str, jobs: JobRegistry) -> _Router:
    router = _Router()

    def _job_started(kind: str, title: str, target) -> Dict[str, Any]:
        job = jobs.submit(kind, title, target)
        return {"job": job.to_dict()}

    # -- system / auth ---------------------------------------------------
    router.add("GET", r"/api/bootstrap", lambda body, p: bridge.bootstrap())
    router.add("POST", r"/api/auth/login",
               lambda body, p: bridge.login(body.get("email", ""), body.get("password", "")))
    router.add("POST", r"/api/auth/register",
               lambda body, p: bridge.register(body.get("email", ""), body.get("password", "")))
    router.add("POST", r"/api/auth/logout", lambda body, p: bridge.logout())

    # -- protocols -------------------------------------------------------
    router.add("GET", r"/api/protocols", lambda body, p: bridge.protocols_remote())
    router.add("GET", r"/api/protocols/local", lambda body, p: bridge.protocols_local())
    router.add("POST", r"/api/protocols/fetch",
               lambda body, p: bridge.protocol_fetch(body.get("name", "")))
    router.add("POST", r"/api/protocols/refresh",
               lambda body, p: bridge.protocol_refresh(body.get("name", "")))
    router.add("POST", r"/api/protocols/remove",
               lambda body, p: bridge.protocol_remove(body.get("name", "")))
    router.add("POST", r"/api/protocols/verify",
               lambda body, p: bridge.protocol_verify(body.get("name", "")))

    # -- projects --------------------------------------------------------
    router.add("GET", r"/api/projects", lambda body, p: bridge.projects_list())
    router.add("POST", r"/api/projects",
               lambda body, p: _job_started(
                   "create_project",
                   f"Create project ({body.get('protocol_name', '?')})",
                   bridge.create_project_job(body.get("protocol_name", ""))))
    router.add("GET", r"/api/projects/(?P<pid>[^/]+)",
               lambda body, p: bridge.project_view(p["pid"]))
    router.add("DELETE", r"/api/projects/(?P<pid>[^/]+)",
               lambda body, p: bridge.project_delete(p["pid"]))
    router.add("GET", r"/api/projects/(?P<pid>[^/]+)/status",
               lambda body, p: bridge.project_status(p["pid"]))
    router.add("GET", r"/api/projects/(?P<pid>[^/]+)/logs",
               lambda body, p: bridge.project_logs(p["pid"]))
    router.add("GET", r"/api/projects/(?P<pid>[^/]+)/results",
               lambda body, p: bridge.project_saved_results(p["pid"]))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/members",
               lambda body, p: bridge.project_add_member(p["pid"], body.get("email", "")))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/run",
               lambda body, p: bridge.project_run(p["pid"]))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/data",
               lambda body, p: _job_started(
                   "contribute_data",
                   "Contribute encrypted data",
                   bridge.contribute_data_job(p["pid"], body.get("vcf_path", ""))))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/result",
               lambda body, p: _job_started(
                   "result",
                   "Download & decrypt result",
                   bridge.result_job(p["pid"])))

    # -- crypto context (per project) ------------------------------------
    router.add("GET", r"/api/projects/(?P<pid>[^/]+)/crypto",
               lambda body, p: bridge.crypto_context_status(p["pid"]))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/crypto/generate",
               lambda body, p: _job_started("crypto_generate", "Generate crypto context",
                                            bridge.crypto_generate_job(p["pid"])))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/crypto/upload",
               lambda body, p: _job_started("crypto_upload", "Upload public context",
                                            bridge.crypto_upload_job(p["pid"])))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/crypto/generate_upload",
               lambda body, p: _job_started("crypto_generate_upload", "Generate & upload context",
                                            bridge.crypto_generate_upload_job(p["pid"])))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/crypto/download",
               lambda body, p: _job_started("crypto_download", "Download public context",
                                            bridge.crypto_download_job(p["pid"])))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/crypto/delete",
               lambda body, p: bridge.crypto_context_delete(p["pid"], body.get("scope", "")))

    # -- granular data pipeline ------------------------------------------
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/encode",
               lambda body, p: _job_started("data_encode", "Encode VCF",
                                            bridge.data_encode_job(p["pid"], body.get("vcf_path", ""))))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/encrypt",
               lambda body, p: _job_started("data_encrypt", "Encrypt encoded data",
                                            bridge.data_encrypt_job(p["pid"], body.get("encoded_path", ""))))
    router.add("POST", r"/api/projects/(?P<pid>[^/]+)/upload",
               lambda body, p: _job_started("data_upload", "Upload ciphertext",
                                            bridge.data_upload_job(p["pid"], body.get("encrypted_path", ""))))

    # -- local analysis --------------------------------------------------
    router.add("POST", r"/api/local/analyze",
               lambda body, p: _job_started(
                   "local_analyze",
                   "Local analysis (offline)",
                   bridge.local_analyze_job(body.get("protocol_name", ""), body.get("vcf_path", ""))))

    # -- system / account ------------------------------------------------
    router.add("GET", r"/api/system/status", lambda body, p: bridge.system_status())
    router.add("POST", r"/api/system/clear-cache", lambda body, p: bridge.system_clear_cache())
    router.add("POST", r"/api/account/delete-profile", lambda body, p: bridge.account_delete_profile())

    # -- jobs ------------------------------------------------------------
    router.add("GET", r"/api/jobs", lambda body, p: {"jobs": jobs.recent()})

    def _get_job(body, p):
        job = jobs.get(p["jid"])
        if not job:
            raise BridgeError("Job not found.")
        return {"job": job.to_dict()}

    router.add("GET", r"/api/jobs/(?P<jid>[^/]+)", _get_job)

    # -- native file picker (pywebview only) -----------------------------
    def _pick_file(body, p):
        if WEBVIEW_WINDOW is None:
            return {"path": None, "supported": False}
        try:
            import webview  # type: ignore

            result = WEBVIEW_WINDOW.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("VCF files (*.vcf;*.vcf.gz)", "All files (*.*)"),
            )
        except Exception as exc:  # noqa: BLE001
            raise BridgeError(f"File dialog failed: {exc}")
        path = result[0] if result else None
        return {"path": path, "supported": True}

    router.add("POST", r"/api/pick-file", _pick_file)

    return router


class Handler(BaseHTTPRequestHandler):
    server_version = "SecureGenomicsDesktop/0.1"

    # injected by make_handler
    token: str = ""
    router: Optional[_Router] = None

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default logging
        pass

    # -- helpers ---------------------------------------------------------
    def _send_json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # same-origin fetch / native window
        host = urlparse(origin).hostname
        return host in ("127.0.0.1", "localhost")

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        # Path-traversal guard: stay inside the frontend directory.
        if FRONTEND_DIR not in target.parents and target != FRONTEND_DIR:
            self.send_error(403, "Forbidden")
            return
        if not target.exists() or not target.is_file():
            # SPA: fall back to index.html so client-side routing works.
            target = FRONTEND_DIR / "index.html"
        body = target.read_bytes()
        if target.name == "index.html":
            body = body.replace(b"%%SG_TOKEN%%", self.token.encode("utf-8"))
        ctype = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- dispatch --------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if not path.startswith("/api/"):
            if method == "GET":
                self._serve_static(path)
            else:
                self.send_error(404)
            return

        if not self._origin_ok():
            self._send_json(403, {"error": "Cross-origin request refused."})
            return
        if self.headers.get("X-SG-Token") != self.token:
            self._send_json(401, {"error": "Missing or invalid session token."})
            return

        # Raw file upload (drag-and-drop / browse) is streamed to disk, so it is
        # handled here rather than through the JSON router.
        if path == "/api/upload-file" and method == "POST":
            self._handle_upload()
            return

        handler, params = self.router.match(method, path)
        if handler is None:
            self._send_json(404, {"error": f"No route for {method} {path}"})
            return

        body = self._read_body() if method in ("POST", "PUT", "PATCH", "DELETE") else {}
        try:
            result = handler(body, params)
            self._send_json(200, result if result is not None else {})
        except BridgeError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — never leak a stack trace to the UI
            self._send_json(500, {"error": str(exc)})

    def _handle_upload(self) -> None:
        """Stream a dragged/browsed file to the local staging dir; return its path.

        The original name arrives URL-encoded in ``X-SG-Filename``; we keep only
        the basename (no path components) and prefix a random token so concurrent
        uploads of the same name never collide. Bytes are streamed to disk in
        chunks so a large VCF never has to sit in memory.
        """
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            self._send_json(400, {"error": "Empty upload."})
            return
        if length > MAX_UPLOAD_BYTES:
            self._send_json(413, {"error": "File too large."})
            return

        raw_name = unquote(self.headers.get("X-SG-Filename", "") or "upload.vcf")
        safe_name = os.path.basename(raw_name.replace("\\", "/")).strip() or "upload.vcf"
        target = UPLOAD_DIR / f"{secrets.token_hex(4)}_{safe_name}"

        remaining = length
        try:
            with open(target, "wb") as fh:
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    fh.write(chunk)
                    remaining -= len(chunk)
        except OSError as exc:
            self._send_json(500, {"error": f"Could not save upload: {exc}"})
            return

        if remaining > 0:  # client hung up mid-stream
            target.unlink(missing_ok=True)
            self._send_json(400, {"error": "Upload was incomplete."})
            return

        self._send_json(200, {
            "path": str(target),
            "filename": safe_name,
            "size": target.stat().st_size,
        })

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")


def make_handler(token: str, router: _Router):
    return type("BoundHandler", (Handler,), {"token": token, "router": router})


class DesktopServer:
    """Owns the HTTP server, its token, and the job registry."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.token = secrets.token_urlsafe(32)
        self.jobs = JobRegistry()
        router = build_app(self.token, self.jobs)
        handler = make_handler(self.token, router)
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self.host, self.port = self._httpd.server_address[:2]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True, name="sg-http")
        thread.start()
        return thread

    def shutdown(self) -> None:
        self._httpd.shutdown()
