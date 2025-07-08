# SecureGenomics CLI - Installation and Usage Guide

**Compute on encrypted data. Zero trust. Full science.**

SecureGenomics CLI is a privacy-preserving genomic analysis platform using Fully Homomorphic Encryption (FHE). It enables researchers to run population-scale studies, GWAS, and allele frequency analysis without ever decrypting sensitive data.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Analysis Modes](#analysis-modes)
- [Core Workflows](#core-workflows)
- [Command Reference](#command-reference)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## Installation

### Requirements

- **Python**: 3.9 or higher
- **Operating System**: macOS, Linux, or Windows
- **Storage**: At least 1GB free space for protocols and data cache
- **Internet**: Required for server-based operations

### Installation Methods

#### 1. Production Installation (Recommended)

```bash
# Install from PyPI
pip install securegenomics

# Verify installation
securegenomics --version
```

#### 2. Development Installation

```bash
# Clone repository
git clone https://github.com/securegenomics/secure-genomics-v2.git
cd secure-genomics-v2

# Install in development mode
pip install -e .

# Optional: Install with FHE support
pip install -e .[fhe]
```

#### 3. Install with Optional Dependencies

```bash
# Install with FHE support for advanced cryptographic operations
pip install securegenomics[fhe]

# Install with development tools
pip install securegenomics[dev]
```

### Verify Installation

```bash
securegenomics --version
securegenomics system status
```

## Quick Start

### 1. Account Setup

```bash
# Register a new account (interactive)
securegenomics auth register

# Or login with existing account
securegenomics auth login

# Check authentication status
securegenomics auth whoami
```

### 2. Explore Available Protocols

```bash
# List all available research protocols
securegenomics protocol list

# View locally cached protocols
securegenomics protocol locals
```

### 3. Run Local Analysis (No Server Required)

```bash
# Download and analyze a VCF file locally
securegenomics local analyze alzheimers-risk sample.vcf
```

### 4. Create Multi-Party Study

```bash
# Create a new project (interactive)
securegenomics project create

# Generate cryptographic context
securegenomics crypto_context generate_upload <project-id>

# Process and upload VCF data
securegenomics data encode_encrypt_upload <project-id> data.vcf

# Start computation
securegenomics project run <project-id>

# Check results
securegenomics project result <project-id>
```

## Authentication

SecureGenomics CLI provides flexible authentication options:

### Interactive Authentication (Recommended)

```bash
# Register new account with secure prompts
securegenomics auth register

# Login with secure prompts
securegenomics auth login

# Quick login (checks if already logged in)
securegenomics auth quick

# Check current user
securegenomics auth whoami

# Logout
securegenomics auth logout
```

### Non-Interactive Authentication (CI/CD)

```bash
# Using command line options
securegenomics auth login --email user@example.com --password mypass --non-interactive

# Using environment variables
export SECUREGENOMICS_EMAIL="user@example.com"
export SECUREGENOMICS_PASSWORD="mypassword"
securegenomics auth login --non-interactive
```

### Authentication Persistence

- **Stay Logged In**: Authentication persists across sessions
- **User-Specific Config**: Each user gets isolated configuration under `~/.securegenomics/<user_id>/`
- **Automatic Detection**: CLI automatically detects authentication state

## Analysis Modes

SecureGenomics CLI supports two distinct analysis modes:

### 1. Local-Only Analysis

**Use Case**: Exploratory analysis, education, offline workflows

**Features**:
- No encryption required
- No server communication
- Instant results
- Perfect for testing and learning

**Example**:
```bash
securegenomics local analyze alzheimers-risk sample.vcf
```

### 2. Aggregated Analysis

**Use Case**: Multi-party studies, privacy-preserving collaboration

**Features**:
- Fully homomorphic encryption
- Multi-party computation
- Cryptographic privacy guarantees
- GDPR/HIPAA compliant

**Example**:
```bash
securegenomics project create
securegenomics data encode_encrypt_upload <project-id> data.vcf
securegenomics project run <project-id>
```

## Core Workflows

### Workflow 1: Local Analysis

```bash
# 1. List available protocols
securegenomics protocol list

# 2. Run local analysis
securegenomics local analyze alzheimers-risk sample.vcf

# 3. View results immediately
```

### Workflow 2: Multi-Party Study (Researcher)

```bash
# 1. Create project
securegenomics project create --protocol alzheimers-risk

# 2. Generate and upload crypto context
securegenomics crypto_context generate_upload <project-id>

# 3. Share project ID with collaborators
securegenomics project view <project-id>

# 4. Wait for data contributions
securegenomics project list --detailed

# 5. Run computation when ready
securegenomics project run <project-id>

# 6. Download results
securegenomics project result <project-id>
```

### Workflow 3: Data Contribution (Collaborator)

```bash
# 1. Process VCF file for specific project
securegenomics data encode_encrypt_upload <project-id> my-data.vcf

# 2. Verify contribution
securegenomics project view <project-id>
```

### Workflow 4: Step-by-Step Data Processing

```bash
# Step 1: Encode VCF using protocol
securegenomics data encode <project-id> data.vcf

# Step 2: Encrypt encoded data
securegenomics data encrypt <project-id> data.vcf.encoded

# Step 3: Upload encrypted data
securegenomics data upload <project-id> data.vcf.encrypted
```

## Command Reference

### Global Options

```bash
securegenomics --help
securegenomics --version
securegenomics --json      # JSON output
securegenomics --quiet     # Suppress output
securegenomics --verbose   # Detailed output
```

### Authentication Commands

```bash
securegenomics auth login [--email EMAIL] [--password PASSWORD]
securegenomics auth register [--email EMAIL] [--password PASSWORD]
securegenomics auth logout
securegenomics auth whoami
securegenomics auth quick
securegenomics auth delete_profile
```

### Protocol Commands

```bash
securegenomics protocol list [--json]
securegenomics protocol fetch <protocol-name>
securegenomics protocol verify <protocol-name>
securegenomics protocol locals
securegenomics protocol remove_local <protocol-name>
securegenomics protocol refresh <protocol-name>
```

### Project Commands

```bash
securegenomics project create [--protocol PROTOCOL] [--description DESC]
securegenomics project list [--detailed]
securegenomics project view <project-id>
securegenomics project run <project-id>
securegenomics project stop <project-id>
securegenomics project job_status <project-id>
securegenomics project result <project-id>
securegenomics project list_saved_results <project-id>
securegenomics project delete <project-id>
```

### Crypto Context Commands

```bash
securegenomics crypto_context generate <project-id>
securegenomics crypto_context upload <project-id>
securegenomics crypto_context download <project-id>
securegenomics crypto_context generate_upload <project-id>
securegenomics crypto_context delete <project-id> [--local] [--server]
```

### Data Processing Commands

```bash
securegenomics data encode <project-id> <vcf-file> [--output-dir DIR]
securegenomics data encrypt <project-id> <encoded-file> [--output-dir DIR]
securegenomics data upload <project-id> <encrypted-file>
securegenomics data encode_encrypt_upload <project-id> <vcf-file> [--output-dir DIR]
```

### Local Analysis Commands

```bash
securegenomics local analyze <protocol-name> <vcf-file>
```

### System Commands

```bash
securegenomics system status
securegenomics system help
```

## Configuration

### Configuration Directory Structure

```
~/.securegenomics/
├── .unauthenticated/          # Temporary space for unauthenticated users
├── alice_c160f8cc/           # alice@example.com's configuration
│   ├── auth.json             # Authentication tokens
│   ├── config.json           # User settings
│   ├── protocols/            # Cached protocols
│   └── projects/             # Project data and contexts
└── bob_a1b2c3d4/             # bob@example.com's configuration
    ├── auth.json
    ├── config.json
    ├── protocols/
    └── projects/
```

### Configuration Options

Edit `~/.securegenomics/<user_id>/config.json`:

```json
{
  "server_url": "https://sg.bozmen.xyz",
  "github_org": "securegenomics",
  "protocol_timeout": 300,
  "upload_chunk_size": 1048576,
  "output_format": "human",
  "auto_verify_protocols": true,
  "max_parallel_uploads": 3
}
```

### Environment Variables

```bash
export SECUREGENOMICS_EMAIL="user@example.com"
export SECUREGENOMICS_PASSWORD="password"
export SECUREGENOMICS_JSON="1"      # Enable JSON output
export SECUREGENOMICS_QUIET="1"     # Suppress output
export SECUREGENOMICS_VERBOSE="1"   # Enable verbose output
```

## Troubleshooting

### Common Issues

#### 1. Authentication Problems

```bash
# Check authentication status
securegenomics auth whoami

# Clear authentication and re-login
securegenomics auth logout
securegenomics auth login

# Check server connectivity
securegenomics system status
```

#### 2. Protocol Issues

```bash
# List available protocols
securegenomics protocol list

# Refresh protocol cache
securegenomics protocol refresh <protocol-name>

# Clear and re-fetch protocol
securegenomics protocol remove_local <protocol-name>
securegenomics protocol fetch <protocol-name>
```

#### 3. Project Issues

```bash
# Check project status
securegenomics project view <project-id>

# Check job status
securegenomics project job_status <project-id>

# List all projects
securegenomics project list --detailed
```

#### 4. Crypto Context Issues

```bash
# Check if context exists locally
securegenomics crypto_context generate <project-id>  # Will fail if exists

# Delete and regenerate
securegenomics crypto_context delete <project-id> --local
securegenomics crypto_context generate_upload <project-id>
```

### Error Messages

| Error | Solution |
|-------|----------|
| "Authentication failed" | Check credentials with `securegenomics auth whoami` |
| "Protocol not found" | Run `securegenomics protocol list` to see available protocols |
| "Project not found" | Verify project ID with `securegenomics project list` |
| "Crypto context already exists" | Use existing context or delete first |
| "Server unreachable" | Check internet connection and `securegenomics system status` |

## Advanced Usage

### Performance Monitoring

All encryption operations provide detailed performance metrics:

```bash
$ securegenomics data encrypt project-123 data.vcf.encoded
🔍 Loading crypto context...
📂 Loading encoded data...  
🔒 Encrypting data...
💾 Saving encrypted data...
✅ Data encrypted using protocol: alzheimers-risk
⚡ Encryption completed in 2.34s (15.2 MB/s)
📁 Encrypted file saved to: data.vcf.encrypted
```

### Batch Processing

```bash
# Process multiple VCF files
for vcf in *.vcf; do
  securegenomics data encode_encrypt_upload <project-id> "$vcf"
done
```

### Automation and CI/CD

```bash
#!/bin/bash
# Automated genomic analysis pipeline

# Set credentials
export SECUREGENOMICS_EMAIL="ci@example.com"
export SECUREGENOMICS_PASSWORD="$CI_PASSWORD"

# Login non-interactively
securegenomics auth login --non-interactive

# Create project
PROJECT_ID=$(securegenomics project create --protocol alzheimers-risk --non-interactive --json | jq -r '.project_id')

# Generate crypto context
securegenomics crypto_context generate_upload $PROJECT_ID

# Process data
securegenomics data encode_encrypt_upload $PROJECT_ID data.vcf

# Run analysis
securegenomics project run $PROJECT_ID

# Wait for completion and get results
securegenomics project result $PROJECT_ID
```

### Multi-Protocol Studies

```bash
# List all protocols with details
securegenomics protocol list --json | jq '.protocols[] | {name, description, analysis_type}'

# Create projects for different protocols
securegenomics project create --protocol alzheimers-risk --description "Alzheimer's Risk Study"
securegenomics project create --protocol cancer-susceptibility --description "Cancer Susceptibility Analysis"
```

### JSON Output for Scripting

```bash
# Get project information as JSON
securegenomics project view <project-id> --json | jq '.project_info'

# List protocols with JSON output
securegenomics protocol list --json | jq '.protocols[].name'

# Check job status programmatically
STATUS=$(securegenomics project job_status <project-id> --json | jq -r '.job_status')
```

## Security and Privacy

### Cryptographic Guarantees

- **Fully Homomorphic Encryption**: Computations on encrypted data
- **Zero-Knowledge**: Server never sees decrypted data
- **Cryptographic Proof**: Every computation is verifiable
- **Hash-Based Provenance**: Tamper-proof computation history

### Privacy Features

- **User Isolation**: Each user has isolated configuration
- **Local Key Storage**: Private keys never leave your machine
- **Secure Transmission**: All communications use HTTPS
- **GDPR/HIPAA Compliance**: Privacy-by-design architecture

### Best Practices

1. **Keep Private Keys Safe**: Never share your private crypto context
2. **Use Strong Passwords**: Enable two-factor authentication when available
3. **Verify Protocols**: Check protocol signatures before use
4. **Monitor Projects**: Regularly check project status and contributors
5. **Clean Up**: Delete unused projects and contexts

## Resources

- **Documentation**: [GitHub Repository](https://github.com/securegenomics/secure-genomics-v2)
- **Protocol Repository**: [SecureGenomics Protocols](https://github.com/orgs/securegenomics/repositories)
- **Design Document**: [docs/design.md](docs/design.md)
- **Privacy Research**: [Genomic Privacy Book](https://github.com/barisozmen/genomic-privacy-book/)

## Support

For issues and questions:

1. Check this guide's [Troubleshooting](#troubleshooting) section
2. Run `securegenomics system help` for built-in help
3. Visit the [GitHub repository](https://github.com/securegenomics/secure-genomics-v2) for issues
4. Check the [protocol repository](https://github.com/orgs/securegenomics/repositories) for protocol-specific questions

