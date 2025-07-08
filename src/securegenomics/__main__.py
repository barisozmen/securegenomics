#!/usr/bin/env python3
"""
Main entry point for SecureGenomics CLI when run as a module.

This allows the CLI to be run as:
    python -m securegenomics

This is useful for:
1. Testing the CLI without installing console scripts
2. Running in environments where console scripts are not available
3. Debugging CLI issues
"""

from securegenomics.cli import main

if __name__ == "__main__":
    main() 