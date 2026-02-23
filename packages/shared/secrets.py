import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Master key must be a 32-byte base64 encoded string
# For testing locally if not provided, we could error. The requirement says:
# "Do NOT store plaintext keys in .env beyond local dev. For dev, allow fallback to .env but warn in README."


def get_master_key() -> bytes:
    master_key_b64 = os.environ.get("NEXUS_MASTER_KEY")
    if not master_key_b64:
        raise RuntimeError(
            "NEXUS_MASTER_KEY environment variable is missing. It must be a 32-byte base64 encoded string."
        )
    try:
        key = base64.b64decode(master_key_b64)
    except Exception:
        raise RuntimeError("NEXUS_MASTER_KEY is not valid base64.")

    if len(key) != 32:
        raise RuntimeError("NEXUS_MASTER_KEY must be exactly 32 bytes when decoded.")
    return key


def encrypt_secret(plaintext: str) -> bytes:
    key = get_master_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # prepend nonce to ciphertext so we can easily decode it later
    return nonce + ciphertext


def decrypt_secret(encrypted_data: bytes) -> str:
    if len(encrypted_data) < 12:
        raise ValueError("Invalid encrypted data length")

    key = get_master_key()
    aesgcm = AESGCM(key)

    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]

    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")
