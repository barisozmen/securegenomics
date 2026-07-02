# Gencrypt Desktop

A native desktop UI for the SecureGenomics (`secgen`) CLI, styled to match the
**gencrypt.xyz** web app (the "Quiet Ledger" look: white canvas, ink-black
primary, IBM Plex, hairlines, a single quiet top nav). It is a thin control room
over the CLI's own engine — **it drives the same manager classes the terminal
commands use**, so it inherits every guarantee the CLI makes and stays in lockstep
with it.

> **Privacy custody is preserved.** Encoding and FHE encryption happen locally.
> The FHE **secret key never leaves this machine** — only ciphertext, the public
> crypto context, and encryption stats are ever uploaded. The desktop adds no
> network paths of its own; it forwards to the CLI.

## Full CLI parity

Everything you can do with `secgen` you can do here. Mapping of CLI commands to
the desktop:

| CLI command group | Desktop surface |
|---|---|
| `auth login/register/logout/whoami` | Sign-in / sign-up screen, account menu |
| `auth delete_profile` | System → Delete profile |
| `protocol list/locals` | Protocols tab (remote + cached badge) |
| `protocol fetch/refresh/remove_local` | Protocol card: Fetch / Refresh |
| `protocol verify` | Protocol card: Verify |
| `project create` | New project (auto keygen + public-context upload) |
| `project list/view` | Projects grid + project detail |
| `project add-member` | Project detail: Add member |
| `project run` / `stop` / `job_status` / `logs` | Project detail: Run / Stop / Latest job |
| `project result` | Project detail: Get result (downloads + decrypts locally) |
| `project list_saved_results` | Project detail: Saved results table |
| `project delete` | Project detail: Delete project |
| `crypto_context generate/upload/generate_upload/download/delete` | Project detail: Crypto context panel |
| `data encode_encrypt_upload` | Project detail: Contribute data |
| `data encode` / `encrypt` / `upload` | Project detail: Advanced (run each step separately) |
| `local analyze` | Local tab (fully offline) |
| `system status` | System tab |
| `system clear-cache` | System → Clear local cache |

Long operations (create + keygen, contribute data, run, decrypt result, crypto
context ops, local analyze) run as background jobs with live step + console
progress; the **Activity** tab lists every job this session.

## Run it

From the repo root, make sure the CLI is available (either installed via
`bash setup.sh`, or just present in `../src` — the launcher finds it either way):

```bash
cd desktop
python3 run.py                 # native window if pywebview is installed, else browser
```

Options:

```bash
python3 run.py --browser       # force the browser fallback
python3 run.py --no-open       # start the server only; open the printed URL yourself
python3 run.py --port 8850     # pin the port (default: an ephemeral free port)
```

For a real native window (no browser chrome):

```bash
pip install pywebview          # then: python3 run.py
```

## How it fits together

```
frontend/ (HTML + CSS + vanilla JS SPA)
        │  fetch() with a per-session X-SG-Token
        ▼
securegenomics_desktop/server.py   ── local 127.0.0.1 HTTP server, token-gated
        │  routes → bridge functions
        ▼
securegenomics_desktop/bridge.py   ── builds a fresh CLI manager per call
        │                              (mirrors the CLI's _build_manager)
        ▼
securegenomics/*  (the CLI engine)  ── AuthManager, ProjectManager, DataManager,
                                       CryptoContextManager, ProtocolManager, …
```

- `securegenomics_desktop/jobs.py` runs long operations on worker threads; the UI
  polls `GET /api/jobs/<id>` for live step + console updates.
- Rich console output printed by the managers is captured and shown in the UI —
  what you see is what the CLI would have printed.

## Security model of the local server

- Binds to `127.0.0.1` only.
- Every `/api/*` call must carry `X-SG-Token`, a random per-session token
  injected into `index.html`. Other local processes / stray web pages can't read
  it, so they can't drive the API (guards against CSRF / DNS-rebinding against
  the local server).
- No endpoint transmits secret keys or plaintext — the bridge only forwards to
  the CLI managers, which enforce the custody boundary.

## Layout

```
desktop/
├── run.py                         # launcher (native window / browser)
├── requirements.txt               # only optional: pywebview
├── securegenomics_desktop/
│   ├── server.py                  # HTTP server + routing + static serving
│   ├── bridge.py                  # CLI-manager wrappers (the "backend")
│   └── jobs.py                    # background-job registry
└── frontend/
    ├── index.html
    ├── styles.css                 # "Quiet Ledger" monochrome design
    └── app.js                     # SPA controller
```
