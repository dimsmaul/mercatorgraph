"""Symmetric encryption for secrets at rest (Fernet).

Used to store repo deploy keys encrypted on the worker. The Fernet key comes from the
environment (``ENCRYPTION_KEY``); it is never written to disk with the ciphertext.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def generate_key() -> str:
    """Generate a new Fernet key (base64 str) — put this in ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def _resolve_key(key: str | None) -> str:
    key = key or os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not set")
    return key


def encrypt(plaintext: str, key: str | None = None) -> str:
    return Fernet(_resolve_key(key).encode()).encrypt(plaintext.encode()).decode()


def decrypt(token: str, key: str | None = None) -> str:
    return Fernet(_resolve_key(key).encode()).decrypt(token.encode()).decode()
