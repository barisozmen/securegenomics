"""
File loading and serialization helpers for SecureGenomics payloads.
"""

import json
from pathlib import Path
from typing import Any


def load_file_smart(file_path: Path) -> Any:
    """Load JSON, text, or binary data using the historical fallback order."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            with open(file_path, "r") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, "rb") as f:
                return f.read()


def save_file_smart(file_path: Path, data: Any) -> None:
    """Save strings, bytes, or JSON-serializable objects."""
    if isinstance(data, str):
        with open(file_path, "w") as f:
            f.write(data)
    elif isinstance(data, (bytes, bytearray)):
        with open(file_path, "wb") as f:
            f.write(data)
    else:
        with open(file_path, "w") as f:
            json.dump(data, f)


def serialize_encrypted_data(data: Any) -> Any:
    """Convert protocol encryption output to the stored byte payload shape."""
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, dict):
        return json.dumps(data).encode("utf-8")
    return data


def write_encrypted_data(file_path: Path, data: Any) -> Any:
    """Serialize encrypted data and write it to disk."""
    encrypted_bytes = serialize_encrypted_data(data)
    with open(file_path, "wb") as f:
        f.write(encrypted_bytes)
    return encrypted_bytes
