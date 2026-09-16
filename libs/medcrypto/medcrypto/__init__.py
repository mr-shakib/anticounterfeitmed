"""Shared cryptographic primitives for the medicine verification platform.

Nothing in this package touches the database, and nothing here decides policy.
It canonicalises records, generates and hashes tokens, and signs/verifies
ML-DSA payloads with mandatory context separation.
"""

from medcrypto.canonical import CanonicalisationError, canonicalise, parse_strict
from medcrypto.contexts import Context
from medcrypto.keys import (
    KeyPair,
    generate_keypair,
    key_id_for_public_key,
    load_private_key,
    load_public_key,
)
from medcrypto.signing import InvalidSignature, sign, verify
from medcrypto.tokens import (
    TOKEN_BYTES,
    TOKEN_TEXT_LENGTH,
    generate_token,
    hash_token,
    is_well_formed_token,
)

__all__ = [
    "CanonicalisationError",
    "canonicalise",
    "parse_strict",
    "Context",
    "KeyPair",
    "generate_keypair",
    "key_id_for_public_key",
    "load_private_key",
    "load_public_key",
    "InvalidSignature",
    "sign",
    "verify",
    "TOKEN_BYTES",
    "TOKEN_TEXT_LENGTH",
    "generate_token",
    "hash_token",
    "is_well_formed_token",
]
