# SecureGenomics Desktop

A native desktop UI for the SecureGenomics (`secgen`) CLI. It is a thin, calm
control room over the CLI's own engine — **it drives the same manager classes
the terminal commands use**, so it inherits every guarantee the CLI makes.

> **Privacy custody is preserved.** Encoding and FHE encryption happen locally.
> The FHE **secret key never leaves this machine** — only ciphertext, the public
> crypto context, and encryption stats are ever uploaded. The desktop adds no
> network paths of its own; it forwards to the CLI.

![Quiet Ledger UI](docs/screenshot-placeholder.txt)

## What you can do

- **Auth** — register / sign in / sign out (Gencrypt account).
- **Projects** — create a project (auto-generates + uploads the *public* crypto
  context), browse, view details, add members, run the computation, download &
  **locally decrypt** results, delete.
- **Contribute data** — pick a VCF and run the local encode → encrypt → upload
  pipeline with live step progress.
- **Protocols** — discover GitHub-backed protocols, fetch / refresh into the
  local cache.
- **Local analysis** — run a cached protocol fully offline (no server, no upload).
- **Activity** — every background job this session, with captured CLI output.

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
