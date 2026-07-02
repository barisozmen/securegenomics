# Gencrypt preprint (companion)

A bioRxiv preprint describes the Gencrypt system that this CLI is one half of:
**"Gencrypt: Separating Custody from Coordination for Privacy-Preserving Genomic
Computation."** It argues that the barrier to encrypted genomic collaboration has
been operational as much as cryptographic, and presents Gencrypt's two-component
design:

- **`secgen` (this repo)** — the client and **custody boundary**. It holds the FHE
  secret key and performs every sensitive operation locally: keypair generation,
  VCF encoding, encryption, decryption, and interpretation. The secret crypto
  context never leaves the machine; only ciphertext, the public context, and
  coarse `encryption_stats` metadata are ever sent to the server.
- **Gencrypt Rails app (`rails_securegenomics`, `gencrypt.xyz`)** — the
  non-custodial **control room** that coordinates projects, ciphertext submissions,
  computation jobs (Solid Queue), domain events, and encrypted-result delivery
  without ever receiving plaintext genomes or secret keys.

Computation semantics are anchored to open-source, SHA-verified GitHub protocol
repositories (`protocol-*`) rather than opaque server code, so every encrypted
workload is auditable and reproducible.

## Where the manuscript lives

The full manuscript is maintained in the companion Rails repository, one Markdown
file per section, under `paper/`:

```
rails_securegenomics/paper/
├── 00-title.md
├── 01-abstract-intro.md
├── 02-background-related.md
├── 03-system-architecture.md
├── 04-crypto-workflow.md
├── 05-security-model.md
├── 06-implementation.md
├── 07-discussion-conclusion.md
├── references.md
└── gencrypt-paper.md      # assembled single document
```

The Implementation and Cryptographic Workflow sections draw directly on this CLI's
`crypto_context.py` (local keygen, public-only upload), `data.py`
(encode → encrypt → upload pipeline), `crypto.py` (raw-binary public-context
download and FHE primitives), and `protocol.py` (commit-SHA + content-hash
verification of GitHub protocols).

Status: alpha-stage research software; the manuscript describes design and
architecture, with quantitative FHE benchmarking as ongoing work.
