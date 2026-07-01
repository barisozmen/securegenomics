# SecureGenomics CLI (`secgen`)

The client half of SecureGenomics/Gencrypt: encrypt genomic data **locally** with
Fully Homomorphic Encryption and contribute ciphertext to researcher-defined
protocols that a server computes on **without ever seeing plaintext or the secret
key**. Tagline: *"Encrypt the data. Send the code. Get the result."*

## The one hard invariant

**The FHE secret key never leaves this machine.** Only ciphertext, the **public**
crypto context, and `encryption_stats` metadata are ever sent to the server. Any
code path, log line, or serialized payload that could carry the private context,
secret key, plaintext VCF/genome, decrypted output, or interpreted result to the
network is a bug in the product's core promise — treat it as such.

## Quick Reference

```bash
git clone https://github.com/securegenomics/securegenomics.git
cd securegenomics && bash setup.sh     # installs `securegenomics` and `secgen`
./refresh_installation.sh              # reinstall editable (pip3 install -e .) after code changes
python -m pytest tests/                # run tests
```

- Python 3.9+. Frameworks: **Typer** (CLI) + **Rich** (output). FHE via **TenSEAL**
  (BFV/CKKS). HTTP via **requests**. **Not on PyPI** — install is git clone.
- Two console entry points, same app: `securegenomics` and `secgen`
  (`pyproject.toml [project.scripts]` → `securegenomics.cli:main`).

## Package layout (`src/securegenomics/`)

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Typer app; command groups `auth` / `protocol` / `project` / `crypto_context` / `data` / `local` / `system`. |
| `auth.py` | Login/register/logout/whoami, token storage, `Authorization: Bearer` headers. **Talks to the server.** |
| `config.py` | `ConfigManager`: per-user dirs, `server_url` resolution, connectivity probe. |
| `project.py` | Create/list/view/delete projects, run/stop, status, logs, result download. **Server.** |
| `data.py` | `encode` → `encrypt` → `upload` pipeline for VCF ciphertext. **Server (upload).** |
| `crypto_context.py` | Generate keypair locally; upload PUBLIC context; delete context. **Server (upload/delete).** |
| `crypto.py` | Download public context; FHE encrypt/decrypt primitives. **Server (download).** |
| `protocol.py` + `github.py` | Fetch/verify protocol repos from the `securegenomics` GitHub org (`protocol-*`). **GitHub, not the app server.** |
| `local.py` | Fully offline `local analyze` (no network). |
| `validation.py` | VCF validation. |

## Per-user state: `~/.securegenomics/`

Everything is namespaced per authenticated user so multiple accounts coexist:

```
~/.securegenomics/
├── .unauthenticated/                 # staging before login
└── <local-part>_<md5(email)[:8]>/    # e.g. alice_3f9c1a2b/
    ├── auth.json      # {token, email, expires_at, user} — chmod 0600
    ├── config.json    # per-user overrides, merged over defaults (e.g. output_format; NOT server_url — that's pinned)
    ├── last_email     # convenience for re-login — chmod 0600
    ├── audit.log
    ├── protocols/<name>/                 # cached protocol code from GitHub
    ├── crypto_context/<project-id>/      # public_*.bin (uploadable) + private_*.bin (LOCAL ONLY)
    └── projects/<project-id>/{data,results}/
```

`config.py:find_most_recent_authenticated_user()` picks the freshest still-valid
token across all user dirs. `token at rest = 0600`; parent dirs should be `0700`.

## Gencrypt API backend (companion repo)

This CLI talks to the **Gencrypt Rails 8** app at **`https://gencrypt.xyz`**
(repo `/Users/barisozmen/development/github/barisozmen/rails_securegenomics`), a
**vanilla Rails JSON API** under `/api` — **not** Django / DRF / SimpleJWT /
Celery. Integration plan + rationale:
`../rails_securegenomics/docs/rfcs/0001-securegenomics-cli-integration.md`.

**The server URL is PINNED to `https://gencrypt.xyz` (API at `/api`).** The user
never supplies a server URL, and it is **never** read from `config.json` — a
stale/old `server_url` left in a per-user config file is ignored entirely, so it
can never misdirect the CLI. The **only** override is the
`SECUREGENOMICS_SERVER_URL` env var (for dev/self-host), which still passes
through the HTTPS guard (`enforce_https`): non-loopback `http://` is refused;
`http://localhost`, `http://127.0.0.1`, `http://[::1]` are the only cleartext
hosts allowed. `ConfigManager.get_server_url()` is the single source of truth —
`enforce_https(SECUREGENOMICS_SERVER_URL)` when set, else the pinned
`DEFAULT_SERVER_URL`.

Contract the CLI must conform to (this is what the backend actually does):
- **Auth token lives at the `token` key** (== `access_token`) with `expires_in`
  (2592000s). It is an **opaque signed Session id, NOT a JWT** — never `jwt.decode`
  it; derive expiry from `expires_in`. There is **no `/api/token/refresh`**; on a
  401, run `secgen login` again (30-day TTL, so this is rare).
- **Login returns HTTP 201** (register too) — accept `200|201`.
- **`context/download` and `result` return RAW BINARY** — read `response.content`;
  do not `response.json()` them. `protocol`/size come from the project info, not
  the download body.
- **Errors are `{ error: { code, message, details? } }`.** Branch on `error.code`
  (`duplicate_filename`, `public_context_exists`, `forbidden`,
  `plaintext_upload_rejected`, `rate_limited`, ...). Keep DRF-style parsing only
  for GitHub calls.
- **List/status/logs shapes:** `projects` list is `{ projects, pagination:{count,...} }`;
  `status` returns the job under `job:{ id }`; `jobs/:id/logs` returns
  `{ job, events, error_summary }`. `profile` returns `{ user:{ email, ... } }`.
- Uploads: multipart `file` + `project_id` + `filename` + `encryption_stats`
  (JSON). Public-context upload: `PATCH /api/projects/:id { public_context: <base64> }`.
- **Security:** HTTPS enforced (refuse non-TLS to any non-loopback host; no
  `--insecure`); the server rejects secret/plaintext param keys with 422 **before
  auth**; the server URL is pinned to `https://gencrypt.xyz` (never from
  `config.json`; only the `SECUREGENOMICS_SERVER_URL` env var can override it).

**Migration status:** RFC 0001 v1 is **implemented** (clean cutover — no
backward-compat shim). The Django assumptions are gone: default host is
`gencrypt.xyz`, tokens are opaque (no `jwt.decode`, no `/api/token/refresh`),
errors parse the Rails `{error:{code,message,details}}` shape, context/result
downloads read raw bytes, and multi-party access goes through the membership
grant (`secgen project add-member`). HTTPS is enforced (loopback excepted).
When you touch `auth/config/project/data/crypto_context/crypto.py`, keep them
aligned to the contract above and the Rails-side cross-ref
(`../rails_securegenomics/CLAUDE.md`) in sync.

## Command surface

- `secgen auth {login,register,logout,whoami,delete_profile}`
- `secgen protocol {list,fetch,verify,locals,remove_local,refresh}` (GitHub-backed)
- `secgen project {create,list,view,delete,run,stop,status,logs,add-member}` (`add-member <project_id> <email>` grants a contributor access; owner-only server-side)
- `secgen crypto_context {generate,upload,generate_upload,download,delete}`
- `secgen data {encode,encrypt,upload,encode_encrypt_upload}`
- `secgen local analyze` (offline) · `secgen system {status,celery-status}`

## Domain knowledge

Load the `securegenomics-expert` skill for the project's design decisions (encrypt/
decrypt flow, token/GTM thesis, threat model, paper). Load `baris-fhe-expert` for
FHE cryptography (scheme math, noise budget, hardware). Allele-frequency is the
lead protocol because it is addition-only (cheapest meaningful encrypted workload).
