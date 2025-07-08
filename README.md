# SecureGenomics™

**Compute on encrypted data. Mathematical guaranties on individual data privacy.**

SecureGenomics Engine is a platform for privacy-preserving genomic analysis using [Fully Homomorphic Encryption (FHE)](https://vitalik.eth.limo/general/2020/07/20/homomorphic.html) and federated computing. It lets scientists run population-scale studies, GWAS, allele frequency analysis — all without ever decrypting sensitive data.

&nbsp;&nbsp;&nbsp;

<p align="center">
  <img src="https://images.emojiterra.com/google/android-12l/512px/1f9ec.png" alt="Image 2" width="240"/>
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://vitalik.eth.limo/images/fhe/HomoEncrypt.png?1" alt="Image 1" width="240"/>
</p>

&nbsp;&nbsp;&nbsp;

Built for
- 🧪 Biobanks — monetize datasets without compromising privacy
- 🧠 Researchers — collaborate across silos, globally, securely
- 🌍 GDPR/HIPAA - safe by design
- 🔐 Zero-trust compute with cryptographic guarantees

&nbsp;&nbsp;&nbsp;

> ⚠️ Alpha stage — active research tool. Contributions & collaborations welcome.

&nbsp;&nbsp;&nbsp;

# Quick Start
Install
```bash
$ pip install git+https://github.com/securegenomics/securegenomics.git
```

## 🚀 Super Simple Workflow

For those who want the quickest path to running secure genomic analysis

For researchers:
```bash
# 1. Login
$ securegenomics login

# 2. Create project (interactive - choose protocol)
$ securegenomics create

# 3. Generate crypto keys
$ securegenomics keygen <project-id>

# 5. Run analysis
$ securegenomics run <project-id>

# 6. Check status
$ securegenomics status <project-id>

# 7. Get results
$ securegenomics result <project-id>
```

For data owners (biobanks, individuals, etc.):
```bash
# 1. Upload data
$ securegenomics upload <project-id> data.vcf
```

## 🚀 Same workflow explained by a scenario

### Bob (scientist) 👨
On his laptop 💻
```bash
# Bob creates a new project
$ securegenomics create
# ☝️ this command, asks Bob to choose an open-source, shareable experiment protocol from https://github.com/securegenomics/ . He chooses `protocol-alzheimers-sensitive-allele-frequency`. All protocols involve scripts for encoding, encryption, computation, decoding, and result interpretation

# Bob generates a public-private crypto context pair
$ securegenomics keygen <project-id> 
# ☝️ this command, under the hood, uploads public crypto context to the SecureGenomics server
```

### Alice (owns sensitive data) 👩
On her computer 🖥️
```bash
# 👨 – Hey Alice, can you contribute to my new experiment with your DNA?
# 👩 – Sure, I love science! But, but I also love my privacy :(
# 👨 – Don't worry, I know an awesome secure tool to do this! Use my <project-id>, encrypt your data and upload to the server!
# 👩 – Cool!

# Alice uploads her genomic data using the complete pipeline
$ securegenomics upload <project-id> data.vcf
# ☝️ under the hood, it encodes, encrypts, and uploads the data in one command

# Or Alice can do it step by step:
# $ securegenomics encode <project-id> data.vcf
# $ securegenomics encrypt <project-id> data.vcf.encoded 
# $ securegenomics data upload <project-id> data.vcf.encrypted

# ℹ️ All above commands use the online protocol code from shared experiment Github repository.
```

### Others (own sensitive data too)
On their local computers 💻
```bash
# Dave, Frank, George, Carol, ... all do the same:
$ securegenomics upload <project-id> their-data.vcf
# ☝️ Each person uploads their encrypted genomic data to the same project
```

### Same Bob again (the scientist) 👨
On his laptop 💻
```bash
# Checks his project, and sees all his friends uploaded– 100s of encrypted genomes! 
$ securegenomics view <project-id>

# Bob now runs the experiment
$ securegenomics run <project-id>
# ☝️ FHE computation, as described in the protocol, is performed on the server.

# After, he downloads and decrypt experiment results with his private key
$ securegenomics result <project-id>
```

What really happened?
- 🙋‍♂️ Bob is happy, because he did an analysis on lots of people's DNA
- 🙋‍♀️ Alice and other contributors are happy, because they kept their DNA private (cryptographically guaranteed)
- 🗄️🔐 Data was always in encrypted form on the server

## Experiment Protocols
Main Hub - [github.com/orgs/securegenomics/repositories](https://github.com/orgs/securegenomics/repositories)

Pick a research protocol above, or create your custom protocol and merge into this repo.

This is the truth base for all computations. You can verify and prove others which computation script was used in your experiment.

> Hyper-sharable, cryptographically verifiable science.

# Resources
- [docs/guide.md](docs/guide.md)
    - for users – installation & commands
- [docs/design.md](docs/design.md)
    - for developers
- [github.com/barisozmen/genomic-privacy-book/](https://github.com/barisozmen/genomic-privacy-book/)
    - Categorization of genomic privacy concerns ([see](https://github.com/barisozmen/genomic-privacy-book/blob/main/02-genomic_privacy_concerns.md))
    - Private vs Public Genomic Data ([see](https://github.com/barisozmen/genomic-privacy-book/blob/main/04a-private_genome_silos.md))
    - FHE mathematical foundations ([fhe](https://github.com/barisozmen/genomic-privacy-book/blob/main/06-homomorphic_encryption_he.md), [math overview](https://github.com/barisozmen/genomic-privacy-book/blob/main/06aa-math_foundations_overview.md), [algebra](https://github.com/barisozmen/genomic-privacy-book/blob/main/06ab-algebra_foundations.md), [lattice-based cryptography](https://github.com/barisozmen/genomic-privacy-book/blob/main/06ac-lattice_based_cryptography_foundations.md))
    - Privacy technologies overview ([see](https://github.com/barisozmen/genomic-privacy-book/blob/main/03-privacy_technologies.md))



# Future Work

## 🔐 Hash-Based Provenance: Scientific Truth as a Chain of Commitments

Treat **every computation** as a cryptographically signed step:
- Every input dataset has a hash
- Every version of your code has a hash
- Each computation step generates a new hash by combining:
    - Data hash
    - Code hash
    - Config/parameter hash
    - Previous step hash (for lineage)

This results in a **chain of composable, tamper-proof proofs** that describe **exactly** how an output came to be — like Git commits, but across data + code + math.

📌 **Even if you don’t share your input data**, others can **verify** that your output hash is consistent with what it should be, given the hash of your data and your open-source computation protocol. 