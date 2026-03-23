"""
Password-protected backup encryption.

Uses Argon2id for key derivation and AES-256-GCM for encryption.
Bundles the NEXUS_MASTER_KEY inside the encrypted payload so restores
are fully self-contained.

File format (encrypted .sql.gz.enc):
  NEXUS_ENC_V1  (12 bytes magic header)
  salt          (16 bytes — Argon2id salt)
  nonce         (12 bytes — AES-GCM nonce)
  ciphertext    (variable — AES-GCM encrypted payload + 16-byte tag)

Payload (before encryption):
  master_key_len  (4 bytes, big-endian uint32)
  master_key      (variable bytes — the NEXUS_MASTER_KEY value, UTF-8)
  sql_gz_data     (remaining bytes — the raw .sql.gz backup)
"""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"NEXUS_ENC_V1"
_SALT_SIZE = 16
_NONCE_SIZE = 12
_KEY_SIZE = 32
MIN_PASSWORD_LENGTH = 8


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from password + salt using scrypt."""
    kdf = Scrypt(salt=salt, length=_KEY_SIZE, n=2**17, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


def encrypt_backup(
    sql_gz_data: bytes,
    password: str,
    master_key: str,
) -> bytes:
    """
    Encrypt a .sql.gz backup with a password.
    Bundles the NEXUS_MASTER_KEY inside the encrypted payload.

    Returns the full encrypted file bytes (magic + salt + nonce + ciphertext).
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    # Build plaintext payload: [master_key_len][master_key][sql_gz_data]
    mk_bytes = master_key.encode("utf-8")
    payload = struct.pack(">I", len(mk_bytes)) + mk_bytes + sql_gz_data

    # Derive AES key
    salt = os.urandom(_SALT_SIZE)
    key = _derive_key(password, salt)

    # Encrypt
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, payload, MAGIC)  # MAGIC as AAD

    return MAGIC + salt + nonce + ciphertext


def decrypt_backup(encrypted_data: bytes, password: str) -> tuple[str, bytes]:
    """
    Decrypt a password-protected backup file.

    Returns (master_key, sql_gz_data).
    Raises ValueError on wrong password or corrupted data.
    """
    # Validate magic header
    if not encrypted_data.startswith(MAGIC):
        raise ValueError("Not a valid Nexus encrypted backup (missing NEXUS_ENC_V1 header).")

    offset = len(MAGIC)
    if len(encrypted_data) < offset + _SALT_SIZE + _NONCE_SIZE + 16:
        raise ValueError("Encrypted backup file is too small to be valid.")

    salt = encrypted_data[offset : offset + _SALT_SIZE]
    offset += _SALT_SIZE

    nonce = encrypted_data[offset : offset + _NONCE_SIZE]
    offset += _NONCE_SIZE

    ciphertext = encrypted_data[offset:]

    # Derive key and decrypt
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)

    try:
        payload = aesgcm.decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:
        raise ValueError("Decryption failed — wrong password or corrupted backup.") from exc

    # Unpack payload: [master_key_len][master_key][sql_gz_data]
    if len(payload) < 4:
        raise ValueError("Decrypted payload is too small.")

    mk_len = struct.unpack(">I", payload[:4])[0]
    if len(payload) < 4 + mk_len:
        raise ValueError("Decrypted payload is corrupted (master key length mismatch).")

    master_key = payload[4 : 4 + mk_len].decode("utf-8")
    sql_gz_data = payload[4 + mk_len :]

    return master_key, sql_gz_data


def is_encrypted_backup(data_or_path) -> bool:
    """Check if data or file starts with the NEXUS_ENC_V1 magic header."""
    if isinstance(data_or_path, bytes | bytearray):
        return data_or_path[: len(MAGIC)] == MAGIC
    # Assume it's a path
    try:
        with open(data_or_path, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except Exception:
        return False
