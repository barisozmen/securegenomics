"""Opt-in live end-to-end test.

This runs scripts/live_e2e.py against an ALREADY-RUNNING Gencrypt Rails server
and asserts it exits 0 (all steps pass). It is SKIPPED unless GENCRYPT_LIVE=1 so
the normal `pytest` suite never touches the network or spawns a server.

It does NOT boot a server: the server must already be up at SECGEN_SERVER_URL
(default http://127.0.0.1:4700).

Run it explicitly:
    GENCRYPT_LIVE=1 SECGEN_SERVER_URL=http://127.0.0.1:4700 \
        python -m pytest tests/test_live_e2e.py -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

LIVE = os.environ.get("GENCRYPT_LIVE") == "1"


@pytest.mark.skipif(
    not LIVE,
    reason="set GENCRYPT_LIVE=1 to run the live end-to-end driver against a running server",
)
def test_live_e2e_driver_passes_all_steps():
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "live_e2e.py"
    assert script.exists(), f"driver missing: {script}"

    env = os.environ.copy()
    env.setdefault("SECGEN_SERVER_URL", "http://127.0.0.1:4700")

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )

    # Surface the driver's step-by-step output in the pytest report.
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    assert proc.returncode == 0, (
        f"live e2e driver failed (exit {proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
