"""
Unit tests for the Secrets Vault crypto layer.

Tests run without database or Docker — pure in-process crypto.
"""
import os
import base64
import pytest

# Set a valid test master key before importing
_test_key = base64.b64encode(os.urandom(32)).decode()
os.environ["VAULT_MASTER_KEY"] = _test_key

from apps.secrets_agent.crypto.envelope import (
    encrypt_secret, decrypt_secret, rotate_secret_dek, EncryptedSecret
)


def test_encrypt_decrypt_roundtrip():
    plaintext = "s3cr3t-p@ssword!"
    enc = encrypt_secret(plaintext)
    assert enc.encrypted_dek
    assert enc.ciphertext
    assert enc.key_version == 1
    result = decrypt_secret(enc)
    assert result == plaintext


def test_encrypt_produces_unique_deks():
    """Each encryption call should produce a different encrypted DEK (random nonce)."""
    enc1 = encrypt_secret("same-value")
    enc2 = encrypt_secret("same-value")
    assert enc1.encrypted_dek != enc2.encrypted_dek
    assert enc1.ciphertext != enc2.ciphertext


def test_plaintext_not_in_ciphertext():
    """Plaintext must not appear verbatim in the ciphertext blob."""
    plaintext = "ultra-secret-api-key-12345"
    enc = encrypt_secret(plaintext)
    assert plaintext.encode() not in enc.ciphertext
    assert plaintext.encode() not in enc.encrypted_dek


def test_wrong_master_key_fails():
    """Decryption with a different master key must fail."""
    enc = encrypt_secret("test-value")
    os.environ["VAULT_MASTER_KEY"] = base64.b64encode(os.urandom(32)).decode()
    try:
        with pytest.raises(ValueError, match="DEK"):
            decrypt_secret(enc)
    finally:
        os.environ["VAULT_MASTER_KEY"] = _test_key


def test_rotate_dek():
    """Rotation should produce a new encrypted blob but same plaintext."""
    original_plaintext = "old-secret"
    enc = encrypt_secret(original_plaintext)
    new_enc = rotate_secret_dek(enc, "new-secret")
    # New blob should be different
    assert new_enc.ciphertext != enc.ciphertext
    # And decryptable
    assert decrypt_secret(new_enc) == "new-secret"


def test_truncated_blob_fails():
    """Tampered/truncated ciphertext must raise ValueError."""
    enc = encrypt_secret("intact")
    bad = EncryptedSecret(
        encrypted_dek=enc.encrypted_dek,
        ciphertext=b"\x00" * 5,
    )
    with pytest.raises(ValueError):
        decrypt_secret(bad)
