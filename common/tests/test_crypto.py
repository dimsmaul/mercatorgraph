import pytest

from ckcommon.crypto import decrypt, encrypt, generate_key


def test_round_trip_with_explicit_key():
    key = generate_key()
    secret = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n"
    token = encrypt(secret, key)
    assert token != secret
    assert decrypt(token, key) == secret


def test_key_from_env(monkeypatch):
    key = generate_key()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    token = encrypt("hunter2")
    assert decrypt(token) == "hunter2"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt("x")


def test_wrong_key_fails(monkeypatch):
    token = encrypt("secret", generate_key())
    with pytest.raises(Exception):
        decrypt(token, generate_key())
