"""ML-DSA key handling.

An ML-DSA-65 private key is a 32-byte seed, which is what makes wrapping it in a
secret manager practical. This module moves keys between that raw form and the
library objects; it deliberately has no opinion about *where* a private key is
stored, because only the signing service is ever allowed to hold one.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import mldsa

ALGORITHM = "ML-DSA-65"

PRIVATE_KEY_SEED_BYTES = 32
PUBLIC_KEY_BYTES = 1952
SIGNATURE_BYTES = 3309

_PRIVATE_CLASS = mldsa.MLDSA65PrivateKey
_PUBLIC_CLASS = mldsa.MLDSA65PublicKey


@dataclass(frozen=True)
class KeyPair:
    """A generated key pair in raw form, plus its derived key id."""

    key_id: str
    private_seed: bytes
    public_key: bytes

    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key).decode("ascii")

    def private_seed_b64(self) -> str:
        """Base64 of the 32-byte seed. Only ever handed to a secret manager."""
        return base64.b64encode(self.private_seed).decode("ascii")


def key_id_for_public_key(public_key: bytes) -> str:
    """Derive a stable key id from the public key.

    Deriving rather than assigning means a key id cannot silently be pointed at
    different key material: the id changes if the key does.
    """
    return "mldsa65-" + hashlib.sha256(public_key).hexdigest()[:32]


def generate_keypair() -> KeyPair:
    private = _PRIVATE_CLASS.generate()
    public_raw = private.public_key().public_bytes_raw()
    return KeyPair(
        key_id=key_id_for_public_key(public_raw),
        private_seed=private.private_bytes_raw(),
        public_key=public_raw,
    )


def load_private_key(seed: bytes) -> mldsa.MLDSA65PrivateKey:
    if len(seed) != PRIVATE_KEY_SEED_BYTES:
        raise ValueError(
            f"expected a {PRIVATE_KEY_SEED_BYTES}-byte seed, got {len(seed)}"
        )
    return _PRIVATE_CLASS.from_seed_bytes(seed)


def load_public_key(raw: bytes) -> mldsa.MLDSA65PublicKey:
    if len(raw) != PUBLIC_KEY_BYTES:
        raise ValueError(
            f"expected a {PUBLIC_KEY_BYTES}-byte public key, got {len(raw)}"
        )
    return _PUBLIC_CLASS.from_public_bytes(raw)
