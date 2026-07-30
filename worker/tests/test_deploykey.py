import os
import stat

from ckcommon.crypto import encrypt, generate_key
from ckworker.deploykey import ssh_env, write_temp_key


def test_write_temp_key_decrypts_and_locks_perms(tmp_path):
    key = generate_key()
    material = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecretbytes\n"
    enc_file = tmp_path / "deploy.enc"
    enc_file.write_text(encrypt(material, key))

    path = write_temp_key(enc_file, key)
    try:
        assert path.read_text() == material
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600
    finally:
        path.unlink(missing_ok=True)


def test_ssh_env_points_at_key():
    env = ssh_env("/tmp/k")
    assert "GIT_SSH_COMMAND" in env
    assert "-i /tmp/k" in env["GIT_SSH_COMMAND"]
