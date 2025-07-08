# Contributing to SecureGenomics

**Welcome to SecureGenomics!** We're excited that you're interested in contributing to privacy-preserving genomic research. This guide will help you get started with contributing to our project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Documentation](#documentation)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our commitment to creating a welcoming and inclusive environment for all contributors. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- **Python**: 3.9 or higher
- **Git**: Latest version
- **GitHub Account**: For submitting pull requests
- **Basic Knowledge**: Python, CLI development, cryptography (helpful but not required)

### Areas Where You Can Contribute

1. **Core CLI Development**: Improve command-line interface functionality
2. **Cryptography**: Enhance FHE implementation and security features
3. **Protocol Development**: Create new genomic analysis protocols
4. **Documentation**: Improve guides, tutorials, and API documentation
5. **Testing**: Add test coverage, integration tests, and performance tests
6. **UI/UX**: Improve user experience and interface design
7. **Performance**: Optimize encryption/decryption and data processing
8. **Bug Fixes**: Fix reported issues and edge cases

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/your-username/securegenomics.git
cd securegenomics

# Add the original repository as upstream
git remote add upstream https://github.com/securegenomics/securegenomics.git
```

### 2. Set Up Development Environment

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install
```

### 3. Verify Installation

```bash
# Run tests to ensure everything works
python -m pytest tests/

# Test CLI functionality
securegenomics --version
securegenomics system status
```

## Contributing Guidelines

### Code Style

- **Follow PEP 8**: Use Python's official style guide
- **Type Hints**: Add type hints for all function parameters and return values
- **Docstrings**: Use Google-style docstrings for all functions and classes
- **Naming**: Use descriptive variable and function names
- **Line Length**: Maximum 88 characters (Black formatter default)

### Example Code Style

```python
def encrypt_genomic_data(
    project_id: str, 
    vcf_file: Path, 
    output_dir: Optional[Path] = None
) -> Path:
    """Encrypt genomic data using FHE for secure computation.
    
    Args:
        project_id: Unique identifier for the project
        vcf_file: Path to the VCF file to encrypt
        output_dir: Directory to save encrypted file (optional)
        
    Returns:
        Path to the encrypted file
        
    Raises:
        CryptoContextError: If crypto context is not available
        ValidationError: If VCF file is invalid
    """
    # Implementation here
    pass
```

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```bash
# Examples of good commit messages
feat: add simplified command aliases for better UX
fix: resolve authentication token expiration issue
docs: update installation guide with new dependencies
test: add integration tests for crypto context management
refactor: simplify project creation workflow
```

### Branch Naming

Use descriptive branch names:
- `feature/simplified-commands`
- `bugfix/auth-token-expiration`
- `docs/contribution-guide`
- `test/integration-crypto-context`

## Pull Request Process

### 1. Before Creating a Pull Request

1. **Create an Issue**: For new features or significant changes, create an issue first to discuss
2. **Check Existing PRs**: Make sure similar work isn't already in progress
3. **Update Documentation**: Ensure your changes are documented
4. **Add Tests**: Include tests for new functionality
5. **Run Tests**: Ensure all tests pass locally

### 2. Creating a Pull Request

1. **Create a Branch**: Create a new branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**: Implement your feature or fix
3. **Commit Changes**: Use conventional commit messages
4. **Push Branch**: Push to your fork
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Open PR**: Create a pull request on GitHub

### 3. Pull Request Template

When creating a PR, include:

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested the CLI commands manually

## Checklist
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
```

### 4. Review Process

1. **Automated Checks**: CI/CD pipeline will run tests and linting
2. **Code Review**: Maintainers will review your code
3. **Feedback**: Address any requested changes
4. **Approval**: Once approved, your PR will be merged

## Issue Reporting

### Bug Reports

When reporting bugs, please include:

```markdown
**Bug Description**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Run command `securegenomics ...`
2. See error message

**Expected Behavior**
What you expected to happen.

**Actual Behavior**
What actually happened.

**Environment**
- OS: [e.g. macOS 12.0]
- Python version: [e.g. 3.9.7]
- SecureGenomics version: [e.g. 0.1.0]

**Additional Context**
Any other context about the problem.
```

### Feature Requests

When suggesting new features:

```markdown
**Feature Description**
A clear and concise description of what you want to happen.

**Use Case**
Describe the specific use case this feature would solve.

**Proposed Solution**
If you have ideas for how it could be implemented.

**Alternatives Considered**
Any alternative solutions or features you've considered.
```

## Development Workflow

### 1. Local Development

```bash
# Keep your fork updated
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature

# Make changes and test
python -m pytest tests/
securegenomics --version

# Commit changes
git add .
git commit -m "feat: add new feature"

# Push to your fork
git push origin feature/your-feature
```

### 2. Testing Your Changes

```bash
# Run unit tests
python -m pytest tests/

# Run integration tests
python -m pytest tests/integration/

# Test CLI commands
securegenomics auth login
securegenomics create
securegenomics local analyze alzheimers-risk sample.vcf

# Test with different Python versions (if available)
tox
```

### 3. Code Quality Checks

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/

# Pre-commit hooks (runs automatically)
pre-commit run --all-files
```

## Testing

### Test Structure

```
tests/
├── unit/                 # Unit tests
│   ├── test_auth.py
│   ├── test_crypto.py
│   └── test_cli.py
├── integration/          # Integration tests
│   ├── test_workflows.py
│   └── test_api.py
├── fixtures/             # Test data
│   ├── sample.vcf
│   └── test_protocols/
└── conftest.py           # Pytest configuration
```

### Writing Tests

```python
import pytest
from securegenomics.auth import AuthManager

def test_login_with_valid_credentials():
    """Test successful login with valid credentials."""
    auth = AuthManager()
    
    # Mock successful authentication
    with patch('securegenomics.auth.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {'token': 'test-token'}
        mock_post.return_value.status_code = 200
        
        result = auth.login('test@example.com', 'password')
        
        assert result is True
        assert auth.is_authenticated()
```

### Test Coverage

We aim for high test coverage:
- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test CLI commands and workflows
- **End-to-End Tests**: Test complete user scenarios

## Documentation

### Types of Documentation

1. **API Documentation**: Docstrings in code
2. **User Guide**: `docs/guide.md`
3. **Design Documentation**: `docs/design.md`
4. **README**: Project overview and quick start
5. **Contributing Guide**: This document

### Documentation Style

- **Clear and Concise**: Use simple, direct language
- **Examples**: Include code examples for all features
- **Step-by-Step**: Break complex processes into steps
- **Cross-References**: Link related sections
- **Up-to-Date**: Keep documentation synchronized with code

### Building Documentation

```bash
# Install documentation dependencies
pip install -e .[docs]

# Generate API documentation
sphinx-apidoc -o docs/api src/

# Build documentation
cd docs
make html
```

## Community

### Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Documentation**: Check the [User Guide](guide.md) and [Design Document](design.md)

### Communication Guidelines

- **Be Respectful**: Treat all community members with respect
- **Be Constructive**: Provide helpful feedback and suggestions
- **Be Patient**: Remember that contributors are volunteers
- **Be Inclusive**: Welcome newcomers and help them get started

### Recognition

We recognize contributors in several ways:
- **Contributors List**: Listed in README and documentation
- **Changelog**: Contributions noted in release notes
- **GitHub**: Contributor badges and statistics
- **Social Media**: Highlighting significant contributions

## Development Philosophy

### Peter Norvig's Principles

This project follows Peter Norvig's principles of elegant software design:

1. **Simplicity**: Choose the simplest solution that works
2. **Clarity**: Code should be self-documenting
3. **Robustness**: Handle edge cases gracefully
4. **Performance**: Optimize for the common case
5. **Maintainability**: Write code that others can understand and modify

### Privacy-First Design

- **Zero-Trust Architecture**: Never trust, always verify
- **Minimal Data Collection**: Collect only necessary information
- **Cryptographic Guarantees**: Use mathematical proofs for security
- **Transparency**: Open source everything, hide nothing

## Getting Started Checklist

- [ ] Read this contributing guide
- [ ] Set up development environment
- [ ] Run existing tests to ensure everything works
- [ ] Look at open issues to find something to work on
- [ ] Join community discussions
- [ ] Make your first contribution (even a small documentation fix!)

## Questions?

If you have questions about contributing, please:

1. Check the [FAQ](guide.md#troubleshooting) in the user guide
2. Search existing GitHub issues
3. Create a new issue with the "question" label
4. Join our community discussions

**Thank you for contributing to SecureGenomics!** Your contributions help make genomic research more collaborative and private. 🧬🔐

---

*Built with ❤️ for privacy-preserving genomic research* 