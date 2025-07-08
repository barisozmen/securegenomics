

# Design and Implementation Details

## Features

- **User-Specific Configuration**: Each authenticated user gets their own isolated configuration directory under `~/.securegenomics/<user_id>/`
- **Persistent Authentication**: Users stay logged in across CLI sessions until explicit logout
- **Seamless Authentication Integration**: Configuration automatically adapts when users log in/out
- **Elegant Directory Management**: Email addresses are sanitized into filesystem-safe identifiers
- **Backward Compatibility**: Graceful handling of unauthenticated state with fallback directories

## Performance Monitoring ⚡

The CLI implements comprehensive performance monitoring following Peter Norvig's principle of elegant measurement.

### Real-time Performance Feedback
Every encryption operation provides detailed performance metrics:
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

### Statistics Captured
- **Phase-by-phase timing**: Context load, data processing, encryption, save operations
- **Throughput calculations**: Real-time MB/s processing rates  
- **System utilization**: Peak memory usage and CPU consumption
- **File metrics**: Input/output sizes, compression ratios
- **Metadata**: Protocol version, Python version, timestamp

### Automatic Server Integration
Performance statistics are automatically:
- Collected during all encryption operations
- Transmitted with encrypted data uploads to server
- Aggregated at project level for research insights
- Used for cost estimation and performance optimization

### Benefits for Users
- **Real-time feedback**: Know exactly how long operations will take
- **Performance optimization**: Identify bottlenecks in your workflow
- **Cost estimation**: Understand computational requirements for large datasets
- **Research contribution**: Provide valuable FHE performance data for genomics research

## Installation

```bash
# Development installation
pip install -e .

# Production installation
pip install securegenomics

# With FHE support
pip install securegenomics[fhe]
```

## Configuration Structure

The CLI uses a user-specific directory structure:

```
~/.securegenomics/
├── .unauthenticated/          # Temporary space for unauthenticated users
├── alice_c160f8cc/           # alice@example.com's configuration
│   ├── auth.json
│   ├── config.json
│   ├── protocols/
│   └── projects/
└── bob_a1b2c3d4/             # bob@example.com's configuration
    ├── auth.json
    ├── config.json
    ├── protocols/
    └── projects/
```

### User Directory Naming

User directories are created using a sanitized version of the email address:
- Extract the local part (before @)
- Clean non-alphanumeric characters
- Append an 8-character hash for uniqueness
- Example: `alice@example.com` → `alice_c160f8cc`

### Authentication Persistence

The CLI provides seamless authentication persistence:

1. **Login Once**: After successful authentication with `securegenomics auth login`, you remain logged in
2. **Automatic Detection**: The CLI automatically detects your authentication state when you run any command
3. **Session Persistence**: Authentication persists across terminal sessions and system restarts
4. **Multiple Users**: If multiple users are authenticated on the same system, the CLI uses the most recently authenticated user
5. **Explicit Logout**: Authentication only expires when tokens expire or you explicitly run `securegenomics auth logout`

**Quick Authentication Check:**
```bash
# Check if you're logged in
securegenomics auth whoami

# Quick login (detects if already authenticated)
securegenomics auth quick
```

## Quick Start

```bash
# Register account (interactive - secure password input)
securegenomics auth register

# Quick login (smart - remembers email, checks if already logged in)
securegenomics auth quick

# Logout
securegenomics auth logout

# Delete account
securegenomics auth delete_profile

# List available protocols
securegenomics protocol list

# List locally available protocols
securegenomics protocol locals
# Remove a locally available protocol
securegenomics protocol remove_local <protocol-name>
# Refresh a locally available protocol (first remove_local, then download)
securegenomics protocol refresh <protocol-name>


# Run local analysis (no server needed)
securegenomics local analyze alzheimers-risk sample.vcf

# Create aggregated project (interactive)
securegenomics project create

# List your projects with detailed information
securegenomics project list

# Generate FHE context for project locally (does not upload)
securegenomics crypto_context generate <project-id>

securegenomics crypto_context delete --local <project-id>
securegenomics crypto_context delete --server <project-id>

# Upload existing local crypto context to server
securegenomics crypto_context upload <project-id>

# Download public crypto context from server
securegenomics crypto_context download <project-id>

# Generate FHE context and upload to server (combined operation)
securegenomics crypto_context generate_upload <project-id>

# VCF Processing - Atomic operations (step-by-step)
securegenomics data encode <project-id> data.vcf                 # Step 1: Encode VCF using protocol
securegenomics data encrypt <project-id> data.vcf.encoded       # Step 2: Encrypt encoded data
securegenomics data upload <project-id> data.vcf.encrypted      # Step 3: Upload encrypted data

# VCF Processing - Combined operation (convenience)
securegenomics data encode_encrypt_upload <project-id> data.vcf  # All 3 steps in one command

# Start computation
securegenomics project run <project-id>

# Check status
securegenomics project job_status <project-id>

# Get results
securegenomics project result <project-id>

# Delete project
securegenomics project delete <project-id>

```

## Command Reference

### Authentication

**Interactive Mode (Recommended)**
```bash
securegenomics auth login           # Prompts securely for credentials
securegenomics auth register        # Interactive registration with password confirmation  
securegenomics auth quick           # Smart login (checks if already logged in)
securegenomics auth logout
securegenomics auth whoami
securegenomics auth delete_profile
```

**Non-Interactive Mode (CI/CD, Scripts)**
```bash
# Using command options
securegenomics auth login --email user@example.com --password mypass --non-interactive
securegenomics auth register --email user@example.com --password mypass --non-interactive

# Using environment variables
export SECUREGENOMICS_EMAIL="user@example.com"
export SECUREGENOMICS_PASSWORD="mypassword"
securegenomics auth login --non-interactive
securegenomics auth register --non-interactive
```

**Security Features**
- 🔒 Hidden password input (not visible in terminal)
- 💾 Email memory (remembers last used email)
- 🚫 No passwords in shell history
- ✅ Password confirmation for registration
- 🔑 JWT token auto-refresh

### Protocols
```bash
securegenomics protocol list                    # List from GitHub
securegenomics protocol fetch <protocol-name>   # Clone from GitHub
securegenomics protocol verify <protocol-name>  # Verify integrity
```

### Projects (Aggregated Analysis)
```bash
# Project Management
securegenomics project create                            # Interactive project creation
securegenomics project list                              # List your projects
securegenomics project list --detailed                   # Detailed view with contributors and job history
securegenomics project view <project-id>                 # View specific project details
securegenomics project delete <project-id>               # Delete project


# Crypto Context Management
securegenomics crypto_context generate <project-id>      # Generate crypto context locally  
securegenomics crypto_context upload <project-id>       # Upload context to server
securegenomics crypto_context download <project-id>     # Download public context from server
securegenomics crypto_context generate_upload <project-id>   # Generate and upload (combined)

# Data Processing (VCF file operations)
securegenomics data encode <project-id> <vcf-file>           # Encode VCF using protocol
securegenomics data encrypt <project-id> <encoded-file>     # Encrypt encoded data
securegenomics data upload <project-id> <encrypted-file>    # Upload encrypted data
securegenomics data encode_encrypt_upload <project-id> <vcf-file> # All 3 steps combined

# Job Management
securegenomics project run <project-id>
securegenomics project job_status <project-id>
securegenomics project result <project-id>
securegenomics project view <project-id>                     # View detailed project information
securegenomics project delete <project-id>                   # Delete project and all data
```

**Enhanced Project Management Features:**
- Rich formatting with color-coded status indicators (pending: yellow, running: blue, completed: green, failed: red)
- Shows crypto context status, VCF file counts, and contributor information
- Displays job history with timestamps when using `--detailed` flag
- Provides summary statistics and next-step guidance
- Includes protocol descriptions and project metadata

### Data Processing (VCF Operations)
```bash
# Atomic operations (step-by-step control)
securegenomics data encode <project-id> <vcf-file>           # Step 1: Encode VCF using protocol
securegenomics data encrypt <project-id> <encoded-file>     # Step 2: Encrypt encoded data
securegenomics data upload <project-id> <encrypted-file>    # Step 3: Upload encrypted data

# Combined operation (convenience)
securegenomics data encode_encrypt_upload <project-id> <vcf-file>  # All 3 steps in one command
```

### Local Analysis
```bash
securegenomics local analyze <protocol-name> <vcf-file>
```

### System
```bash
securegenomics system status
securegenomics system help
```

## Configuration

CLI uses user-specific directories under `~/.securegenomics/`:

```
~/.securegenomics/
├── .unauthenticated/          # Temporary space for unauthenticated users
├── alice_c160f8cc/           # alice@example.com's configuration
│   ├── auth.json             # JWT tokens (secure, 600 permissions)
│   ├── config.json           # CLI preferences  
│   ├── last_email            # Last used email (for convenience)
│   ├── audit.log             # Audit trail of all operations
│   ├── protocols/            # Cached protocol code
│   │   ├── alzheimers-risk/
│   │   └── allele-frequency/
│   ├── crypto_context/       # Project-specific FHE context
│   │   ├── {project-uuid}/
│   │   └── ...
│   └── projects/             # Project data
└── bob_a1b2c3d4/             # bob@example.com's configuration
    └── ... (same structure)
```

**Multi-User Support**: Each authenticated user gets their own isolated directory, ensuring complete data separation and security. Directory names are generated from email addresses using a sanitization algorithm that preserves readability while ensuring filesystem safety.

## Output Formats

- **Human mode**: Rich tables, colors, progress bars (default)
- **JSON mode**: `--json` flag for programmatic usage
- **Quiet mode**: `--quiet` for CI/CD pipelines

```bash
securegenomics --json protocol list
securegenomics --quiet local analyze alzheimers-risk data.vcf
```

## Security

- All protocols verified via SHA256 before execution
- Authentication tokens stored in `~/.securegenomics/`
- Project crypto contexts isolated per project
- All operations logged to `~/.securegenomics/audit.log`

## Development

### Design Principles

This implementation follows Peter Norvig's principles of elegant software design:

1. **Minimal Complexity**: Simple state management with clear user transitions
2. **Robust Defaults**: Graceful fallback to unauthenticated mode  
3. **Seamless Integration**: Authentication and configuration work together transparently
4. **Clear Separation**: Each user's data is completely isolated

### Multi-User Configuration API

The `ConfigManager` class provides methods for managing user-specific configurations:

```python
from securegenomics.config import ConfigManager

# Initialize (automatically detects current user from auth tokens)
config = ConfigManager()

# Set authenticated user (called automatically during login)
config.set_authenticated_user("alice@example.com")

# Get current user
user = config.get_current_user()  # Returns email or None

# Clear user (called automatically during logout)  
config.clear_authenticated_user()

# List all configured users
users = ConfigManager.list_configured_users()  # Returns list of emails
```

### Testing

```bash
python -m pytest tests/
```

## Architecture

The CLI is organized into core modules:

- `auth.py`: Authentication management
- `protocol.py`: GitHub protocol discovery and caching
- `crypto.py`: FHE encryption/decryption
- `project.py`: Multi-party project management
- `local.py`: Local-only analysis
- `cli.py`: Command-line interface 

## Troubleshooting

### Getting Better Error Messages

If you encounter generic error messages, you can enable more detailed debugging:

```bash
# Enable debug mode for detailed request/response information
export SECUREGENOMICS_DEBUG=1
securegenomics crypto_context download <project-id>

# Enable verbose output
export SECUREGENOMICS_VERBOSE=1
securegenomics project list

# Check system status and configuration
securegenomics system status
```

### Common Issues

#### "No context available for this project"
This means the project doesn't have a crypto context uploaded yet. Solutions:
1. If you're the project owner: Generate and upload a context
   ```bash
   securegenomics crypto_context generate_upload <project-id>
   ```
2. If you're a contributor: Ask the project owner to upload the crypto context first

#### "Authentication failed" 
Check if you're logged in and tokens are valid:
```bash
securegenomics auth whoami
# If not logged in:
securegenomics auth login
```

#### "Project not found"
Verify the project ID and your access:
```bash
securegenomics project list
```

### Debug Logs

Server-side logs (for administrators):
- Located in server logs: `/logs/django.log`
- All crypto context operations are logged with user and project details
- Enable Django debug mode for detailed error traces

Client-side debug information:
- Set `SECUREGENOMICS_DEBUG=1` for HTTP request/response details
- Set `SECUREGENOMICS_VERBOSE=1` for detailed operational logs
- Check audit logs: `~/.securegenomics/<user>/audit.log`

## Output Formats 
