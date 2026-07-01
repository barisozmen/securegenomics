#!/usr/bin/env python3
"""Live end-to-end driver for the SecureGenomics CLI against a running Gencrypt server.

This exercises the REAL CLI HTTP layer (AuthManager / ProjectManager and the
documented Rails API endpoints) end-to-end against an ALREADY-RUNNING Rails
server. It deliberately skips all FHE crypto / protocol / GitHub work: every
place where a CLI manager method would need a real TenSEAL context or a cloned
protocol repo, we instead push OPAQUE bytes to the same documented endpoint,
over the same authenticated request path the CLI uses (reusing AuthManager's
bearer header). The point is to prove the HTTP client + response parsing +
Rails contract line up, not the cryptography.

Usage:
    SECGEN_SERVER_URL=http://127.0.0.1:4700 python scripts/live_e2e.py

Exit code 0 iff every step passes; otherwise a summary is printed and exit 1.

Never starts/stops/restarts the server. The only external process it spawns is
a single short `bin/rails runner` (step 7) to fabricate an encrypted result
with known opaque bytes, so the owner's GET /api/result round-trips real bytes.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

# --------------------------------------------------------------------------- #
# 0. Sandbox everything BEFORE importing the CLI or constructing any manager.
# --------------------------------------------------------------------------- #

SERVER_URL = os.environ.get("SECGEN_SERVER_URL", "http://127.0.0.1:4700").rstrip("/")

# Absolute repo locations (this driver is repo-pinned by design).
SECGEN_REPO = Path(__file__).resolve().parents[1]
RAILS_REPO = Path(
    os.environ.get(
        "GENCRYPT_RAILS_REPO",
        "/Users/barisozmen/development/github/barisozmen/rails_securegenomics",
    )
)

# Capture the REAL home before we clobber it — the `bin/rails runner` subprocess
# needs a genuine HOME for bundler / version managers.
REAL_HOME = os.environ.get("HOME", str(Path.home()))

# Fresh temp HOME so ~/.securegenomics is fully sandboxed. We give each actor
# (owner, contributor) its own HOME subdir so the CLI's "most-recent
# authenticated user" auto-selection is unambiguous inside a single process.
SANDBOX = Path(tempfile.mkdtemp(prefix="secgen-live-e2e-"))
OWNER_HOME = SANDBOX / "owner"
CONTRIB_HOME = SANDBOX / "contrib"
OWNER_HOME.mkdir(parents=True, exist_ok=True)
CONTRIB_HOME.mkdir(parents=True, exist_ok=True)

# Default HOME to the sandbox owner dir; use_home() switches per actor.
os.environ["HOME"] = str(OWNER_HOME)

# Make the in-repo package importable even without an editable install.
sys.path.insert(0, str(SECGEN_REPO / "src"))

import requests  # noqa: E402  (after sandboxing, before managers is fine)

import securegenomics.config as cfg  # noqa: E402

# Force EVERY manager onto the e2e server. Managers cache the server_url at
# __init__, so this MUST run before any manager is constructed. Loopback http is
# allowed by the CLI's own https guard, and replacing the method sidesteps it
# entirely for whatever URL the operator points us at.
cfg.ConfigManager.get_server_url = lambda self, _u=SERVER_URL: _u  # type: ignore[assignment]

from securegenomics.auth import AuthManager  # noqa: E402
from securegenomics.project import ProjectManager  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

PASSWORD = "e2e-password-123"


class StepError(Exception):
    """A step-level assertion failure with a human-readable detail."""


def use_home(home: Path) -> None:
    """Point ~ (and therefore ~/.securegenomics) at one actor's sandbox home."""
    os.environ["HOME"] = str(home)


def opaque(size: int, tag: bytes) -> bytes:
    """Deterministically-tagged opaque bytes that trip no plaintext-genomic guard.

    Prefix with an ASCII tag + NUL so it can never resemble a VCF/BAM/SAM/GFF
    magic signature, then pad with random bytes so it is clearly not plaintext.
    """
    body = os.urandom(max(0, size - len(tag) - 1))
    return tag + b"\x00" + body


def auth_headers(home: Path) -> dict:
    """Fresh bearer + base headers for the actor whose home is `home`.

    Constructs a brand-new AuthManager (as a fresh CLI invocation would), so the
    token migrated into the authenticated-user dir is resolved correctly.
    """
    use_home(home)
    am = AuthManager()
    headers = am._get_auth_headers()
    if not headers:
        raise StepError(f"no authenticated headers available for HOME={home}")
    return headers


def stored_token(home: Path) -> str:
    use_home(home)
    am = AuthManager()
    token = am.get_token()
    if not token:
        raise StepError(f"no stored token for HOME={home}")
    return token


# --------------------------------------------------------------------------- #
# Step registry
# --------------------------------------------------------------------------- #

RESULTS: list[tuple[int, str, bool, str]] = []

# Shared state threaded across steps.
STATE: dict = {}


def record(n: int, name: str, ok: bool, detail: str) -> None:
    RESULTS.append((n, name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"STEP {n} {name}: {status} {detail}", flush=True)


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #


def step1_register_owner() -> str:
    email = f"owner-{uuid.uuid4().hex[:12]}@e2e.gencrypt.test"
    use_home(OWNER_HOME)
    if not AuthManager().register(email, PASSWORD):
        raise StepError("register(owner) returned False")

    # Fresh manager, as a subsequent CLI command would use.
    use_home(OWNER_HOME)
    who = AuthManager().whoami()
    if not who or who.get("email", "").lower() != email.lower():
        raise StepError(f"whoami returned {who!r}, expected email {email!r}")

    STATE["owner_email"] = email
    return f"registered + authenticated as {email}; whoami confirms owner"


def step2_create_project() -> str:
    use_home(OWNER_HOME)
    pm = ProjectManager()
    protocol_name = "e2e-allele"
    pid = pm.create(protocol_name)
    if not pid or not isinstance(pid, str):
        raise StepError(f"create() returned bad project id: {pid!r}")

    STATE["project_id"] = pid
    STATE["protocol_name"] = protocol_name
    return f"project_id={pid} protocol_name={protocol_name}"


def step3_upload_public_context() -> str:
    pid = STATE["project_id"]
    ctx_bytes = opaque(64, b"E2E-CTX")
    STATE["ctx_bytes"] = ctx_bytes
    b64 = base64.b64encode(ctx_bytes).decode("ascii")

    # Mirror CryptoContextManager.upload_crypto_context's request path exactly,
    # but with opaque bytes instead of a real TenSEAL public context.
    headers = auth_headers(OWNER_HOME)
    resp = requests.patch(
        f"{SERVER_URL}/api/projects/{pid}",
        json={"public_context": b64},
        headers=headers,
        timeout=60,
        allow_redirects=False,
    )
    if resp.status_code != 200:
        raise StepError(f"PATCH /api/projects/{pid} -> {resp.status_code} {resp.text[:300]}")

    # Confirm the project now reports has_context via the real CLI reader.
    use_home(OWNER_HOME)
    info = ProjectManager()._get_project_info(pid)
    if not info.get("has_context"):
        raise StepError(f"project has_context is falsy after upload: {info.get('has_context')!r}")

    return f"PATCH 200 ({len(ctx_bytes)} opaque bytes); project.has_context=True"


def step4_add_contributor() -> str:
    contrib_email = f"contrib-{uuid.uuid4().hex[:12]}@e2e.gencrypt.test"
    use_home(CONTRIB_HOME)
    if not AuthManager().register(contrib_email, PASSWORD):
        raise StepError("register(contributor) returned False")
    STATE["contrib_email"] = contrib_email

    # Owner grants membership via the real CLI add-member path.
    use_home(OWNER_HOME)
    member = ProjectManager().add_member(STATE["project_id"], contrib_email)
    if not member or member.get("email", "").lower() != contrib_email.lower():
        raise StepError(f"add_member returned {member!r}, expected email {contrib_email}")

    return f"contributor {contrib_email} registered; owner granted membership (member={member})"


def step5_contributor_download_and_upload() -> str:
    pid = STATE["project_id"]

    # (a) Contributor downloads the public context (raw bytes) and it must match.
    headers = auth_headers(CONTRIB_HOME)
    resp = requests.get(
        f"{SERVER_URL}/api/context/download",
        params={"project_id": pid},
        headers=headers,
        timeout=60,
        allow_redirects=False,
    )
    if resp.status_code != 200:
        raise StepError(f"GET /api/context/download -> {resp.status_code} {resp.text[:300]}")
    if resp.content != STATE["ctx_bytes"]:
        raise StepError(
            f"downloaded context bytes differ (got {len(resp.content)}B, "
            f"expected {len(STATE['ctx_bytes'])}B)"
        )

    # (b) Contributor uploads an opaque ciphertext (multipart file).
    ct_bytes = opaque(96, b"E2E-CIPHERTEXT")
    files = {"file": ("ciphertext.bin", ct_bytes, "application/octet-stream")}
    data = {"project_id": pid, "filename": "ciphertext.bin"}
    up = requests.post(
        f"{SERVER_URL}/api/upload",
        files=files,
        data=data,
        headers=auth_headers(CONTRIB_HOME),
        timeout=120,
        allow_redirects=False,
    )
    if up.status_code not in (200, 201):
        raise StepError(f"POST /api/upload -> {up.status_code} {up.text[:300]}")
    body = up.json()
    server_filename = body.get("server_filename")
    if not body.get("success") or not server_filename:
        raise StepError(f"upload response missing success/server_filename: {body!r}")

    return (
        f"context download matched ({len(resp.content)}B); "
        f"ciphertext uploaded (server_filename={server_filename})"
    )


def step6_run_and_status() -> str:
    pid = STATE["project_id"]
    use_home(OWNER_HOME)
    job_id = ProjectManager().run(pid)
    if not job_id:
        raise StepError("run() returned no job id")
    STATE["job_id"] = job_id

    use_home(OWNER_HOME)
    status = ProjectManager().get_job_status(pid)
    job = status.get("job") or {}
    if str(job.get("id")) != str(job_id):
        raise StepError(f"status job id {job.get('id')!r} != run job id {job_id!r}")
    if status.get("status") in (None, "", "no_jobs"):
        raise StepError(f"status did not reflect the job: {status.get('status')!r}")

    return f"run job_id={job_id}; status.job.id matches; status={status.get('status')!r}"


def step7_result_roundtrip() -> str:
    pid = STATE["project_id"]
    result_bytes = opaque(128, b"E2E-RESULT")
    STATE["result_bytes"] = result_bytes

    # Fabricate a completed job + EncryptedResult with KNOWN opaque bytes via a
    # single `bin/rails runner`. We read the ComputationJob/EncryptedResult
    # contract straight from the Rails repo: transition the latest job to
    # completed and attach an ActiveStorage-backed EncryptedResult.
    ruby = (
        'require "base64"; require "digest"; require "stringio";'
        'pid = ENV.fetch("GENCRYPT_E2E_PROJECT_ID");'
        'bytes = Base64.strict_decode64(ENV.fetch("GENCRYPT_E2E_RESULT_B64"));'
        'project = Project.find(pid);'
        'job = project.computation_jobs.order(created_at: :desc, id: :desc).first;'
        'abort("E2E_NO_JOB") unless job;'
        'job.encrypted_result&.destroy;'
        'job.update_columns(status: "completed", finished_at: Time.current, failure_code: nil, error_summary: nil);'
        'fname = "encrypted_result_#{project.id}_#{job.id}.bin";'
        'blob = ActiveStorage::Blob.create_and_upload!(io: StringIO.new(bytes), filename: fname, content_type: "application/octet-stream");'
        'res = job.build_encrypted_result(filename: fname, byte_size: bytes.bytesize, sha256: Digest::SHA256.hexdigest(bytes), content_type: "application/octet-stream");'
        'res.artifact.attach(blob);'
        'res.save!;'
        'puts "E2E_RESULT_OK job=#{job.id} result=#{res.id} sha=#{res.sha256} bytes=#{bytes.bytesize}"'
    )

    env = os.environ.copy()
    env["HOME"] = REAL_HOME  # bundler / version managers need a real home
    env["BUNDLE_GEMFILE"] = str(RAILS_REPO / "Gemfile")
    env["RAILS_ENV"] = "development"
    env["GENCRYPT_E2E_PROJECT_ID"] = pid
    env["GENCRYPT_E2E_RESULT_B64"] = base64.b64encode(result_bytes).decode("ascii")

    proc = subprocess.run(
        ["bin/rails", "runner", ruby],
        cwd=str(RAILS_REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0 or "E2E_RESULT_OK" not in proc.stdout:
        raise StepError(
            "result fabrication failed "
            f"(exit {proc.returncode}): stdout={proc.stdout.strip()[:300]!r} "
            f"stderr={proc.stderr.strip()[-400:]!r}"
        )
    runner_line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith("E2E_RESULT_OK")), ""
    )

    # Owner downloads the encrypted result and the raw bytes must match exactly.
    resp = requests.get(
        f"{SERVER_URL}/api/result",
        params={"project_id": pid},
        headers=auth_headers(OWNER_HOME),
        timeout=60,
        allow_redirects=False,
    )
    if resp.status_code != 200:
        raise StepError(f"GET /api/result -> {resp.status_code} {resp.text[:300]}")
    if resp.content != result_bytes:
        raise StepError(
            f"downloaded result bytes differ (got {len(resp.content)}B, "
            f"expected {len(result_bytes)}B)"
        )

    return f"fabricated [{runner_line}]; GET /api/result returned identical {len(result_bytes)} bytes"


def step8_logout_revokes_session() -> str:
    # Capture the live token BEFORE logout so we can prove server-side revocation.
    old_token = stored_token(OWNER_HOME)

    # Sanity: the token works right now.
    pre = requests.get(
        f"{SERVER_URL}/api/profile",
        headers={"Authorization": f"Bearer {old_token}", "Accept": "application/json"},
        timeout=30,
        allow_redirects=False,
    )
    if pre.status_code != 200:
        raise StepError(f"pre-logout /api/profile -> {pre.status_code} (expected 200)")

    # Real CLI logout: revokes the Session server-side, then wipes local auth.
    use_home(OWNER_HOME)
    AuthManager().logout()

    # The previously-valid token must now be rejected (session revoked -> 401).
    post = requests.get(
        f"{SERVER_URL}/api/profile",
        headers={"Authorization": f"Bearer {old_token}", "Accept": "application/json"},
        timeout=30,
        allow_redirects=False,
    )
    if post.status_code != 401:
        raise StepError(
            f"post-logout /api/profile -> {post.status_code} (expected 401 revoked)"
        )

    return "pre-logout 200; post-logout old bearer rejected with 401 (session revoked)"


STEPS = [
    (1, "register_owner", step1_register_owner),
    (2, "create_project", step2_create_project),
    (3, "upload_public_context", step3_upload_public_context),
    (4, "add_contributor", step4_add_contributor),
    (5, "contributor_download_and_upload", step5_contributor_download_and_upload),
    (6, "run_and_status", step6_run_and_status),
    (7, "result_roundtrip", step7_result_roundtrip),
    (8, "logout_revokes_session", step8_logout_revokes_session),
]


def main() -> int:
    print(f"# Live E2E against {SERVER_URL}  (sandbox HOME under {SANDBOX})", flush=True)
    aborted = False
    for n, name, fn in STEPS:
        if aborted:
            record(n, name, False, "skipped (earlier step failed)")
            continue
        try:
            detail = fn()
            record(n, name, True, detail)
        except StepError as e:
            record(n, name, False, str(e))
            aborted = True
        except Exception as e:  # noqa: BLE001 — surface any unexpected error clearly
            record(n, name, False, f"unexpected error: {e}")
            traceback.print_exc()
            aborted = True

    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    total = len(STEPS)
    print("", flush=True)
    print(f"# Summary: {passed}/{total} steps passed", flush=True)
    if passed != total:
        for n, name, ok, detail in RESULTS:
            if not ok:
                print(f"  - FAILED step {n} {name}: {detail}", flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
