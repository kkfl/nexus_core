"""
Envelope Encryption for the Secrets Vault.

Crypto model:
- KEK (Key Encryption Key / master key): loaded from VAULT_MASTER_KEY env var.
  32 bytes, base64-encoded. NEVER stored in DB. V2: swap for KMS/HSM.
- DEK (Data Encryption Key): random 32 bytes per secret. Encrypted with KEK.
- Both KEK→DEK and DEK→secret use AES-256-GCM with a random 12-byte nonce.
- Layout on disk: nonce (12 bytes) || ciphertext (variable) + GCM tag (16 bytes).

INVARIANT: Plaintext secret values NEVER leave this module without being
           explicitly requested via decrypt_secret(). They are NEVER logged.
"""

from __future__ import annotations

import base64
import contextlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12
_KEY_SIZE = 32


def _get_kek() -> bytes:
    """Load and validate the Key Encryption Key from the environment."""
    raw = os.environ.get("VAULT_MASTER_KEY") or os.environ.get("NEXUS_MASTER_KEY")
    if not raw:
        raise RuntimeError(
            "VAULT_MASTER_KEY (or NEXUS_MASTER_KEY) environment variable is required. "
            'Generate with: python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"'
        )
    # Support both hex-encoded (64 hex chars → 32 bytes) and base64-encoded keys
    key: bytes | None = None
    if len(raw) == 64:
        with contextlib.suppress(ValueError):
            key = bytes.fromhex(raw)
    if key is None:
        try:
            key = base64.b64decode(raw)
        except Exception as exc:
            raise RuntimeError("VAULT_MASTER_KEY is not valid hex or base64.") from exc
    if len(key) != _KEY_SIZE:
        raise RuntimeError(f"VAULT_MASTER_KEY must decode to exactly {_KEY_SIZE} bytes.")
    return key


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce || ciphertext+tag."""
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ct


def _aes_gcm_decrypt(key: bytes, blob: bytes) -> bytes:
    """AES-256-GCM decrypt from nonce || ciphertext+tag blob."""
    if len(blob) < _NONCE_SIZE + 16:
        raise ValueError("Encrypted blob is too short to be valid.")
    nonce, ct = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


@dataclass
class EncryptedSecret:
    """Container for an envelope-encrypted secret."""

    encrypted_dek: bytes  # AES-GCM(KEK, random_dek)
    ciphertext: bytes  # AES-GCM(DEK, plaintext_secret)
    key_version: int = 1  # increment when KEK rotates


def encrypt_secret(plaintext: str, key_version: int = 1) -> EncryptedSecret:
    """
    Envelope-encrypt a plaintext secret.
    1. Generate a random 256-bit DEK.
    2. Encrypt plaintext with DEK (AES-GCM).
    3. Encrypt DEK with KEK (AES-GCM).
    Returns EncryptedSecret — no plaintext ever stored.
    """
    kek = _get_kek()
    dek = os.urandom(_KEY_SIZE)
    ciphertext = _aes_gcm_encrypt(dek, plaintext.encode("utf-8"))
    encrypted_dek = _aes_gcm_encrypt(kek, dek)
    return EncryptedSecret(
        encrypted_dek=encrypted_dek, ciphertext=ciphertext, key_version=key_version
    )


def decrypt_secret(enc: EncryptedSecret) -> str:
    """
    Decrypt an envelope-encrypted secret.
    1. Decrypt DEK using KEK.
    2. Decrypt plaintext using DEK.
    IMPORTANT: caller is responsible for not logging the returned value.
    """
    kek = _get_kek()
    try:
        dek = _aes_gcm_decrypt(kek, enc.encrypted_dek)
    except Exception as exc:
        raise ValueError("Failed to decrypt DEK — wrong master key or corrupted data.") from exc
    try:
        plaintext_bytes = _aes_gcm_decrypt(dek, enc.ciphertext)
    except Exception as exc:
        raise ValueError(
            "Failed to decrypt secret value — DEK decryption succeeded but ciphertext is corrupted."
        ) from exc
    return plaintext_bytes.decode("utf-8")


def rotate_secret_dek(old_enc: EncryptedSecret, plaintext: str) -> EncryptedSecret:
    """
    Re-encrypt a secret with a brand-new DEK (same KEK).
    Call this during rotation. Returns a new EncryptedSecret.
    """
    # Decrypt old to confirm we have the correct plaintext, then re-encrypt fresh.
    _ = decrypt_secret(old_enc)  # validation only
    return encrypt_secret(plaintext, key_version=old_enc.key_version)
