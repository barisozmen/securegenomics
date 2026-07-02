#!/usr/bin/env python3
"""End-to-end demo of the SecureGenomics CLI (`secgen`) against the Gencrypt app.

Runs the two real product scenarios, end to end, driving the actual `secgen`
binary the way a user would — with real FHE crypto (TenSEAL) and real VCF data:

  Scenario 1 — Single player (local, offline)
      One person computes their own Alzheimer's polygenic risk score entirely on
      their laptop. Nothing leaves the machine. (`secgen local analyze`)

  Scenario 2 — Multi player (encrypted, cloud)
      A researcher and two data owners compute an *allele frequency* across their
      genomes without anyone ever seeing anyone else's genome. Each data owner
      encrypts locally; the Gencrypt server homomorphically SUMS the ciphertext
      (it never holds the secret key); the researcher decrypts the aggregate.
      This exercises the whole webapp/cloud path:
        secgen register / create (keygen + upload public context)
        secgen project add-member
        secgen upload         (encode -> encrypt -> upload ciphertext)
        server-side FHE runner (RunComputationJob -> circuit.compute)
        secgen status / result (download -> decrypt -> interpret)

The custody boundary is the whole point: the FHE secret key never leaves a data
owner/researcher machine. Only ciphertext + the PUBLIC context reach the server.

Usage:
    # runs against the production Gencrypt server (https://gencrypt.xyz) by default
    python scripts/demo.py
    # point at a local dev server instead (bin/dev must be running)
    SECUREGENOMICS_SERVER_URL=http://localhost:3490 python scripts/demo.py

Exit code 0 iff both scenarios pass.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration / environment
# --------------------------------------------------------------------------- #

RAILS_REPO = Path(
    os.environ.get(
        "GENCRYPT_RAILS_REPO",
        "/Users/barisozmen/development/github/barisozmen/rails_securegenomics",
    )
)
SECGEN_REPO = Path(__file__).resolve().parents[1]
REAL_HOME = os.environ.get("HOME", str(Path.home()))
PASSWORD = "Demo-Passw0rd-123"
RESEARCHER_EMAIL = "res@example.com"
OWNER_EMAILS = ["user1@example.com", "user2@example.com"]
AGG_PROTOCOL = "alzheimers-sensitive-allele-frequency"   # aggregated (multi-player)
LOCAL_PROTOCOL = "alzheimer-prs"                          # local (single-player)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

C_OK, C_ERR, C_HEAD, C_DIM, C_END = "\033[92m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"


def resolve_server_url() -> str:
    # Default to the pinned production server (https://gencrypt.xyz). Only an
    # explicit SECUREGENOMICS_SERVER_URL override (e.g. a local `bin/dev` server)
    # points the demo elsewhere.
    if os.environ.get("SECUREGENOMICS_SERVER_URL"):
        return os.environ["SECUREGENOMICS_SERVER_URL"].rstrip("/")
    return "https://gencrypt.xyz"


def resolve_secgen() -> list[str]:
    exe = shutil.which("secgen")
    if exe:
        return [exe]
    return [sys.executable, "-m", "securegenomics"]


def resolve_github_token() -> str:
    """Return a GitHub token for protocol fetches, or "" to force anonymous.

    The demo makes many GitHub REST calls — each party re-fetches and re-verifies
    the protocol under its OWN $HOME, so the cache isn't shared — which blows the
    60 req/hr anonymous limit partway through. Prefer an authenticated token
    (5000 req/hr). Resolution order:
      1. GITHUB_TOKEN from the real shell env, if the user exported one.
      2. `gh auth token`, if the GitHub CLI is installed and logged in.
      3. "" — force anonymous, blanking the var so a stale/expired token left in
         src/securegenomics/.env (which python-decouple reads) can't 401 fetches.
    """
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    gh = shutil.which("gh")
    if gh:
        try:
            proc = subprocess.run(
                [gh, "auth", "token"], capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
    return ""


SERVER_URL = resolve_server_url()
SECGEN = resolve_secgen()
GITHUB_TOKEN = resolve_github_token()
# The inline `bin/rails runner` fallback only makes sense for a LOCAL dev server
# (it drives the local Rails DB). Against a remote server (e.g. gencrypt.xyz) the
# computation must happen ON that server's own worker; never fall back locally.
IS_LOCAL_SERVER = any(h in SERVER_URL for h in ("localhost", "127.0.0.1", "[::1]"))

# --------------------------------------------------------------------------- #
# Small harness
# --------------------------------------------------------------------------- #


class DemoError(Exception):
    pass


def head(title: str) -> None:
    print(f"\n{C_HEAD}{'━' * 78}\n{title}\n{'━' * 78}{C_END}", flush=True)


def step(msg: str) -> None:
    print(f"\n{C_DIM}▶ {msg}{C_END}", flush=True)


def ok(msg: str) -> None:
    print(f"  {C_OK}✔ {msg}{C_END}", flush=True)


def _print_secgen_command(args: tuple[str, ...]) -> None:
    printable = " ".join(["secgen", *args])
    print(f"    {C_DIM}$ {printable}{C_END}", flush=True)


def _print_secgen_output(out: str) -> None:
    for line in out.strip().splitlines():
        print(f"      {C_DIM}{line}{C_END}", flush=True)


def secgen(
    home: Path,
    *args: str,
    server: bool = True,
    check: bool = True,
    show: bool = True,
) -> str:
    """Invoke the real `secgen` binary as `home`'s user; return combined output."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    # Protocols are public repos. The demo hits GitHub many times (each party
    # re-fetches/verifies the protocol under its own HOME), so anonymous access
    # (60 req/hr) runs out mid-run. Use an authenticated token when we can find
    # one (5000 req/hr); otherwise blank the var so a stale/expired token in
    # src/securegenomics/.env (read by python-decouple) can't 401 fetches.
    # os.environ overrides decouple's .env. See resolve_github_token().
    env["GITHUB_TOKEN"] = GITHUB_TOKEN
    if server:
        env["SECUREGENOMICS_SERVER_URL"] = SERVER_URL
    else:
        env.pop("SECUREGENOMICS_SERVER_URL", None)
    if show:
        _print_secgen_command(args)
    proc = subprocess.run(
        [*SECGEN, *args], env=env, capture_output=True, text=True, timeout=600
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if show:
        _print_secgen_output(out)
    if check and proc.returncode != 0:
        printable = " ".join(["secgen", *args])
        raise DemoError(f"`{printable}` exited {proc.returncode}")
    return out


def create_or_login_demo_account(home: Path, email: str) -> None:
    """Create the fixed demo account, or log in if it already exists."""
    register_args = (
        "register",
        "--non-interactive",
        "--email",
        email,
        "--password",
        PASSWORD,
    )
    register_out = secgen(home, *register_args, check=False, show=False)
    if "Successfully registered" in register_out:
        _print_secgen_command(register_args)
        _print_secgen_output(register_out)
        return

    login_args = (
        "login",
        "--non-interactive",
        "--email",
        email,
        "--password",
        PASSWORD,
    )
    login_out = secgen(home, *login_args, check=False, show=False)
    if "Successfully logged in" in login_out:
        _print_secgen_command(login_args)
        _print_secgen_output(login_out)
        return

    _print_secgen_command(register_args)
    _print_secgen_output(register_out)
    _print_secgen_command(login_args)
    _print_secgen_output(login_out)
    raise DemoError(f"could not authenticate fixed demo account {email}")


def wait_for_terminal_status(home: Path, project_id: str, timeout: int = 90) -> str | None:
    """Poll `secgen status` until the server's job reaches a terminal state.

    Returns "completed"/"failed" once the job settles, or the last-seen status
    (or None) on timeout. Used to detect whether the running server computes the
    job on its own (async worker path) before we fall back to the inline helper.
    """
    import time

    deadline = time.time() + timeout
    last: str | None = None
    while time.time() < deadline:
        out = secgen(home, "status", project_id, check=False)
        m = re.search(r"status:\s*([a-z_]+)", out.lower())
        if m:
            last = m.group(1)
            if last in ("completed", "failed"):
                return last
        time.sleep(3)
    return last


def rails_worker_compute(project_id: str, protocol_dir: Path) -> str:
    """Run the server-side FHE computation via the configured runner (the same
    RunComputationJob path a Solid Queue worker uses in production)."""
    runner = RAILS_REPO / "script" / "gencrypt_fhe_runner.py"
    env = dict(os.environ)
    env["HOME"] = REAL_HOME                      # bundler / rbenv need a real home
    env["BUNDLE_GEMFILE"] = str(RAILS_REPO / "Gemfile")
    env["RAILS_ENV"] = "development"
    env["GENCRYPT_RUNNER_COMMAND"] = f"{sys.executable} {runner}"
    env["GENCRYPT_PROTOCOL_DIR"] = str(protocol_dir)   # offline + deterministic
    print(f"    {C_DIM}$ bin/rails runner script/gencrypt_run_worker.rb {project_id}{C_END}", flush=True)
    proc = subprocess.run(
        ["bin/rails", "runner", "script/gencrypt_run_worker.rb", project_id],
        cwd=str(RAILS_REPO), env=env, capture_output=True, text=True, timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.strip().splitlines():
        print(f"      {C_DIM}{line}{C_END}", flush=True)
    if proc.returncode != 0 or "status=completed" not in out:
        raise DemoError(f"server-side compute failed (exit {proc.returncode})")
    return out


# --------------------------------------------------------------------------- #
# Synthetic-but-real VCF data (real APOE/AD rsIDs, chosen genotypes)
# --------------------------------------------------------------------------- #

TARGET_ROWS = [
    ("19", 44908684, "rs429358", "T", "C"),
    ("19", 44908822, "rs7412", "C", "T"),
    ("19", 44892362, "rs2075650", "A", "G"),
    ("19", 44906745, "rs199768005", "C", "A"),
    ("19", 44888997, "rs6857", "C", "T"),
    ("8", 27464519, "rs11136000", "C", "T"),
    ("11", 85868640, "rs3851179", "G", "A"),
    ("2", 127892810, "rs6733839", "C", "T"),
    ("1", 207577223, "rs6656401", "G", "A"),
    ("19", 1050875, "rs3764650", "T", "G"),
]
VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##FILTER=<ID=PASS,Description="All filters passed">\n'
    + "".join(f"##contig=<ID={c}>\n" for c in ("1", "2", "8", "11", "19"))
    + '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
)


def write_vcf(path: Path, genotypes: list[str]) -> None:
    lines = [VCF_HEADER]
    for (chrom, pos, rsid, ref, alt), gt in zip(TARGET_ROWS, genotypes):
        lines.append(f"{chrom}\t{pos}\t{rsid}\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n")
    path.write_text("".join(lines))


# --------------------------------------------------------------------------- #
# Scenario 1 — single player (local, offline)
# --------------------------------------------------------------------------- #


def scenario_single_player(work: Path) -> None:
    head("SCENARIO 1 — Single player (local Alzheimer's PRS, fully offline)")
    home = work / "solo"
    home.mkdir(parents=True, exist_ok=True)
    vcf = work / "solo_genome.vcf"
    # A person carrying a couple of AD risk alleles.
    write_vcf(vcf, ["0/1", "0/0", "1/1", "0/0", "0/1", "1/1", "0/1", "0/0", "0/1", "0/0"])
    ok(f"wrote sample genome with the 10 AD target variants -> {vcf.name}")

    step("Compute the polygenic risk score locally — no login, no network")
    out = secgen(home, "local", "analyze", "-p", LOCAL_PROTOCOL, "-f", str(vcf), server=False)

    if "polygenic risk score" not in out.lower() and "PRS" not in out:
        raise DemoError("local analyze did not produce a PRS interpretation")
    if "RISK" not in out.upper():
        raise DemoError("local analyze did not produce a risk assessment")
    ok("local PRS computed and interpreted entirely on-device")


# --------------------------------------------------------------------------- #
# Scenario 2 — multi player (encrypted, cloud)
# --------------------------------------------------------------------------- #


def scenario_multi_player(work: Path) -> None:
    head("SCENARIO 2 — Multi player (encrypted allele frequency across 3 parties)")

    researcher = work / "researcher"
    owners = [work / "owner1", work / "owner2"]
    for d in [researcher, *owners]:
        d.mkdir(parents=True, exist_ok=True)
    r_email = RESEARCHER_EMAIL
    o_emails = OWNER_EMAILS

    # Two data owners' genomes. The alt-allele count per variant is sum(GT); the
    # protocol sums these homomorphically across owners. Derive the ground truth
    # DIRECTLY from the genotypes we actually write+upload (not a hardcoded list),
    # so a green run can only mean the FHE compute processed *these* inputs.
    owner_genotypes = [
        ["0/1", "0/0", "1/1", "0/0", "0/1", "1/1", "0/1", "0/0", "0/1", "0/0"],
        ["1/1", "0/1", "0/1", "0/0", "1/1", "0/1", "0/0", "1/1", "0/0", "0/1"],
    ]

    def alt_count(gt: str) -> int:
        return sum(int(a) for a in gt.replace("|", "/").split("/") if a.isdigit())

    expected_sum = [sum(alt_count(gts[i]) for gts in owner_genotypes)
                    for i in range(len(TARGET_ROWS))]
    expected_genomes = len(owner_genotypes)
    vcfs = [work / "owner1_genome.vcf", work / "owner2_genome.vcf"]
    for path, gts in zip(vcfs, owner_genotypes):
        write_vcf(path, gts)

    # A local checkout of the protocol for the server-side runner (offline path).
    # Only the LOCAL dev-server fallback (rails_worker_compute) needs it; the
    # remote server computes with its own protocol checkout.
    protocol_dir = work / "protocol"
    if IS_LOCAL_SERVER:
        subprocess.run(
            ["git", "clone", "--depth", "1", "-q",
             f"https://github.com/securegenomics/protocol-{AGG_PROTOCOL}", str(protocol_dir)],
            check=True, timeout=120,
        )

    # 1. Create all accounts first. The researcher creates/runs the project;
    # data owners are created before the project is configured.
    step("Create the researcher and data-owner accounts")
    create_or_login_demo_account(researcher, r_email)
    for od, oe in zip(owners, o_emails):
        create_or_login_demo_account(od, oe)
    ok("researcher and data-owner accounts are ready")

    # 2. Researcher creates the project (auto keygen + public-context upload).
    step("Researcher creates the project (auto-generates the FHE keypair, "
         "uploads only the PUBLIC context)")
    create_out = secgen(researcher, "create", "--non-interactive", "-p", AGG_PROTOCOL)
    ids = UUID_RE.findall(create_out)
    if not ids:
        raise DemoError("could not find the created project id in `secgen create` output")
    pid = ids[0]
    ok(f"project {pid} created; public crypto context uploaded")

    # The secret key must exist locally and must NOT have been uploaded.
    priv = researcher / ".securegenomics"
    private_files = list(priv.rglob("private_crypto_context.bin"))
    if not private_files:
        raise DemoError("researcher has no local private context — keygen did not run")
    ok(f"private (secret-key) context stays local: {private_files[0].relative_to(researcher)}")

    # 3. Researcher grants the already-created data owners membership.
    step("Researcher grants the data owners project membership")
    for oe in o_emails:
        secgen(researcher, "project", "add-member", pid, oe)
    ok("both data owners are now members and can contribute encrypted genomes")

    # 4. Each data owner encodes + encrypts + uploads (ciphertext only).
    step("Each data owner encrypts their genome locally and uploads ONLY ciphertext")
    for od, vcf in zip(owners, vcfs):
        secgen(od, "upload", pid, str(vcf))
    ok("2 encrypted genome submissions uploaded (server holds ciphertext only)")

    # 5. Researcher starts the run; the server-side worker computes homomorphically.
    step("Researcher starts the computation; the Gencrypt worker sums the "
         "ciphertext homomorphically (no secret key on the server)")
    run_out = secgen(researcher, "run", pid, check=False)   # enqueue via the real CLI/API
    if "Job ID" not in run_out and "Started computation" not in run_out:
        raise DemoError("`secgen run` did not confirm the computation was enqueued")

    # Prefer the REAL async path: if the running server has a runner configured
    # (a freshly-started `bin/dev` exports GENCRYPT_RUNNER_COMMAND), its OWN async
    # worker computes the job — proving "the Rails app runs the Python runner".
    # Only if the server can't self-compute do we fall back to the inline dev
    # worker helper (bin/rails runner), and we say so loudly.
    final_status = wait_for_terminal_status(researcher, pid, timeout=180 if not IS_LOCAL_SERVER else 90)
    if final_status == "completed":
        ok("the server computed the job on its own worker (async/Solid Queue path) "
           "and produced an ENCRYPTED aggregate result")
    elif not IS_LOCAL_SERVER:
        # Remote server (e.g. gencrypt.xyz): the compute MUST run there. Do not
        # fall back to a local bin/rails runner (that would hit the local DB).
        secgen(researcher, "status", pid, check=False)
        raise DemoError(
            f"remote server {SERVER_URL} did not compute the job "
            f"(status={final_status or 'timeout'}). Its Solid Queue worker needs a "
            "working GENCRYPT_RUNNER_COMMAND (python+TenSEAL). Check `secgen status`/job logs."
        )
    else:
        why = f"job status={final_status or 'timeout'}"
        step(f"local server did not self-compute ({why}); falling back to the inline "
             "dev worker (bin/rails runner) with the FHE runner configured")
        worker_out = rails_worker_compute(pid, protocol_dir)   # configured FHE runner does the work
        m = re.search(r"submissions=(\d+)", worker_out)
        if not m or int(m.group(1)) != expected_genomes:
            raise DemoError(
                f"worker processed {m.group(1) if m else '?'} submissions, "
                f"expected {expected_genomes}"
            )
        ok(f"inline worker ran the homomorphic circuit over {expected_genomes} "
           "ciphertext submissions and produced an ENCRYPTED aggregate result")

    # 6. Researcher checks status and downloads + decrypts + interprets.
    step("Researcher checks status and fetches the result (decrypts locally)")
    secgen(researcher, "status", pid, check=False)
    result_out = secgen(researcher, "result", pid)

    # Verify the decrypted aggregate matches the known genotype sums.
    decrypted = None
    for f in sorted((researcher / ".securegenomics").rglob("decrypted_result_*.json")):
        try:
            import json
            decrypted = json.loads(f.read_text())
        except Exception:
            continue
    if not isinstance(decrypted, list):
        raise DemoError("could not read a decrypted result vector from the researcher's store")
    got_sum, got_genomes = decrypted[:-1], decrypted[-1]
    print(f"      {C_DIM}decrypted aggregate = {got_sum} over {got_genomes} genomes{C_END}")
    if got_sum != expected_sum or got_genomes != expected_genomes:
        raise DemoError(
            f"aggregate mismatch: got sum={got_sum} genomes={got_genomes}, "
            f"expected sum={expected_sum} genomes={expected_genomes}"
        )
    ok(f"decrypted allele-count aggregate matches the ground truth {expected_sum} "
       f"over {expected_genomes} genomes")
    if "allele_frequenc" not in result_out and "num_genomes" not in result_out:
        raise DemoError("`secgen result` did not print an interpreted allele-frequency report")
    ok("researcher obtained real allele frequencies without ever seeing a raw genome")


# --------------------------------------------------------------------------- #


def main() -> int:
    print(f"{C_HEAD}SecureGenomics CLI — end-to-end demo{C_END}")
    print(f"  server : {SERVER_URL}")
    print(f"  secgen : {' '.join(SECGEN)}")
    print(f"  rails  : {RAILS_REPO}")
    print(f"  github : {'authenticated (5000 req/hr)' if GITHUB_TOKEN else 'anonymous (60 req/hr — may hit rate limits)'}")

    # Fail fast if the server isn't up.
    try:
        import urllib.request
        with urllib.request.urlopen(f"{SERVER_URL}/up", timeout=8) as r:
            if r.status != 200:
                raise RuntimeError(f"/up returned {r.status}")
    except Exception as e:
        hint = "Start it with `bin/dev`." if IS_LOCAL_SERVER else "Check your network / the server status."
        print(f"{C_ERR}Server not reachable at {SERVER_URL} ({e}). {hint}{C_END}")
        return 1

    work = Path(tempfile.mkdtemp(prefix="secgen-demo-"))
    results: list[tuple[str, bool, str]] = []
    try:
        for name, fn in [("single-player", scenario_single_player),
                         ("multi-player", scenario_multi_player)]:
            try:
                fn(work)
                results.append((name, True, ""))
            except DemoError as e:
                results.append((name, False, str(e)))
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                results.append((name, False, f"unexpected: {e}"))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    head("SUMMARY")
    for name, passed, detail in results:
        mark = f"{C_OK}PASS{C_END}" if passed else f"{C_ERR}FAIL{C_END}"
        print(f"  {mark}  {name}{('  — ' + detail) if detail else ''}")
    all_ok = all(p for _, p, _ in results)
    print(f"\n{'🎉 ' if all_ok else ''}{'both scenarios passed' if all_ok else 'demo failed'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
