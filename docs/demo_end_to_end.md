# End-to-end demo (`scripts/demo.py`)

One script that proves the whole SecureGenomics stack works — the `secgen` CLI,
the Gencrypt Rails app, and the FHE compute path — by running the two real
product scenarios against a live server with real TenSEAL crypto and real VCF
data.

```bash
# 1. start the Gencrypt app (in the rails_securegenomics repo)
bin/dev

# 2. run the demo (in this repo)
python scripts/demo.py
```

Exit code `0` iff both scenarios pass. The demo auto-detects the dev server port;
override with `SECUREGENOMICS_SERVER_URL=http://localhost:PORT`.

## What it does

### Scenario 1 — single player (local, offline)
`secgen local analyze -p alzheimer-prs -f <vcf>` computes an Alzheimer's
polygenic risk score entirely on-device. No login, no network, nothing leaves
the machine.

### Scenario 2 — multi player (encrypted, cloud)
A researcher and two data owners compute an **allele frequency** across their
genomes without anyone seeing anyone else's genome:

1. `secgen register` / `secgen create` — the researcher creates the project;
   `create` auto-generates the FHE keypair and uploads **only the public
   context**. The secret key stays on the researcher's machine.
2. `secgen project add-member` — the researcher grants each data owner
   membership (uploading requires membership).
3. `secgen upload <project> <vcf>` — each data owner encodes → encrypts →
   uploads **ciphertext only** (public context downloaded, genome encrypted
   locally with TenSEAL BFV).
4. `secgen run` enqueues a `ComputationJob`; a worker runs the protocol's
   `circuit.compute` homomorphically over the ciphertext (server never has the
   secret key) and stores an **encrypted** aggregate.
5. `secgen status` / `secgen result` — the researcher downloads the encrypted
   result and decrypts + interprets it **locally** with the private context.

The demo verifies the decrypted aggregate equals the known genotype sums of the
two input genomes (`[3,1,3,0,3,3,1,2,1,1]` over 2 genomes → allele frequencies),
so a green run means the FHE math actually round-tripped — not that bytes merely
moved.

### Custody boundary (the product's whole thesis)
The FHE **secret key never leaves the client**. You can prove the server can't
read the result: its stored public context reports `has_secret_key() == False`,
and decrypting the stored result with it raises
`ValueError: ...doesn't hold a secret_key`.

## How the server computes (the FHE runner)

`secgen run` / `POST /api/run` enqueue a `ComputationJob`; `RunComputationJob`
stages the public context + ciphertext into a work dir and invokes
`GENCRYPT_RUNNER_COMMAND`. The bundled runner lives in the Rails repo:

- `script/gencrypt_fhe_runner.py` — reads the job manifest, clones the
  researcher's `protocol-*` repo, runs its `circuit.compute(encrypted_datasets,
  public_context)` over ciphertext only, and writes the encrypted result. It
  never reads a secret key / private context (and refuses private-looking files).
- `script/gencrypt_run_worker.rb` — a dev helper that runs a project's
  `ComputationJob` inline with the runner configured, so you don't need a
  separate Solid Queue worker. In production a Solid Queue worker started with
  `GENCRYPT_RUNNER_COMMAND` set does this automatically.

`bin/dev` resolves an absolute, TenSEAL-capable `python3` and exports
`GENCRYPT_RUNNER_COMMAND=<that python> script/gencrypt_fhe_runner.py`, so a
freshly-started dev server processes `secgen run` end-to-end on its own via its
in-process async worker (override the interpreter with `GENCRYPT_RUNNER_PYTHON`,
or the whole command with `GENCRYPT_RUNNER_COMMAND`).

`scripts/demo.py` therefore **prefers the real async path**: after `secgen run`
it polls `secgen status` and, if the running server computes the job on its own,
uses that result. Only if the server has no runner configured (job never
settles / fails) does it fall back to the inline `gencrypt_run_worker.rb` helper,
and it says so. Either way, a green run means the FHE math round-tripped through
real ciphertext.

## Troubleshooting

- **`GitHub API error: Bad credentials`** on any protocol fetch/`local analyze`:
  a stale/expired token in `src/securegenomics/.env` (`GITHUB_TOKEN=...`) is
  being picked up by `python-decouple`. The protocol repos are public — delete
  or refresh that token, or run with `GITHUB_TOKEN=` to force anonymous access
  (what the demo does). An expired token 401s every GitHub call.
- **`register`/`login` returns HTTP 500, `unknown attribute 'client' for
  Session`**: the running dev server booted before the `add client to sessions`
  migration. Restart `bin/dev` (or touch a model file to trigger a reload) so it
  picks up the applied migration.
- **`server-side compute failed` / `runner exited status 2`**: the runner needs
  TenSEAL and network (to clone the protocol). `RunComputationJob` now captures
  the runner's **stderr** and surfaces a sanitized tail in the job's
  `error_summary` (visible via `secgen status` / `secgen job_logs`), so the real
  cause — e.g. "the FHE backend TenSEAL is not importable by this runner" — is
  reported directly. `GENCRYPT_RUNNER_DEBUG_LOG=<path>` still captures a fuller
  human-readable trace.
