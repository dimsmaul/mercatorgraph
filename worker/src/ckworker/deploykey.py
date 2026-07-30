"""Decrypt a repo deploy key to a temp file and build the git SSH env for cloning."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from ckcommon.crypto import decrypt


def write_temp_key(encrypted_key_path: str | Path, enc_key: str | None = None) -> Path:
    """Decrypt an encrypted deploy key file to a 0600 temp file. Returns its path."""
    ciphertext = Path(encrypted_key_path).read_text()
    material = decrypt(ciphertext, enc_key)
    if not material.endswith("\n"):
        material += "\n"
    fd, path = tempfile.mkstemp(prefix="ck-deploykey-")
    os.write(fd, material.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return Path(path)


def ssh_env(key_path: str | Path) -> dict[str, str]:
    return {
        "GIT_SSH_COMMAND": (
            f"ssh -i {key_path} -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new"
        )
    }
