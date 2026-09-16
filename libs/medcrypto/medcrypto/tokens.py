"""Package token generation and hashing.

A token is a possession credential: 32 cryptographically random bytes, encoded
unpadded Base64url. It is never an incrementing serial and never a hash of
predictable product data.

Only ``hash_token`` output may be persisted. Raw tokens live in the print
generation path and in transient request memory, and nowhere else -- not in
audit events, reports, analytics or logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

TOKEN_BYTES = 32
TOKEN_TEXT_LENGTH = 43  # unpadded base64url length of 32 bytes

_TOKEN_RE = re.compile(rf"\A[A-Za-z0-9_-]{{{TOKEN_TEXT_LENGTH}}}\Z")


def generate_token() -> str:
    """Return a fresh unpadded Base64url token carrying 32 random bytes."""
    return base64.urlsafe_b64encode(secrets.token_bytes(TOKEN_BYTES)).rstrip(b"=").decode("ascii")


def is_well_formed_token(token: str) -> bool:
    """Cheap structural check, used before any database lookup.

    This rejects obviously malformed input early. It says nothing about whether
    the token exists.
    """
    return bool(_TOKEN_RE.match(token))


def hash_token(token: str) -> bytes:
    """Return ``SHA-256(raw_token)``, the only form that may be stored.

    The digest is taken over the token's ASCII text, which is exactly what the
    QR carries and what the activation credential commits to.
    """
    if not is_well_formed_token(token):
        raise ValueError("malformed token")
    return hashlib.sha256(token.encode("ascii")).digest()


def tokens_equal(left: str, right: str) -> bool:
    """Constant-time comparison for two raw tokens."""
    return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))


def digests_equal(left: bytes, right: bytes) -> bool:
    """Constant-time comparison for two token digests."""
    return hmac.compare_digest(left, right)
