"""ML-DSA signing and verification.

Two rules are enforced here rather than left to callers:

* a context is always required, so a signature made for one record type cannot
  verify as another;
* verification operates on the exact bytes received, never on a re-serialisation.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature as _LibInvalidSignature

from medcrypto.contexts import Context
from medcrypto.keys import load_private_key, load_public_key


class InvalidSignature(Exception):
    """Raised when a signature does not verify, for any reason."""


def sign(private_seed: bytes, context: Context, payload: bytes) -> bytes:
    """Sign canonical ``payload`` under ``context``.

    ``payload`` must already be canonical; this function does not canonicalise,
    because the bytes that are signed have to be the bytes that are sent.
    """
    if not isinstance(context, Context):
        raise TypeError("context must be a Context member")
    key = load_private_key(private_seed)
    return key.sign(payload, context=context.value)


def verify(public_key: bytes, context: Context, payload: bytes, signature: bytes) -> None:
    """Verify ``signature`` over ``payload`` under ``context``.

    Returns ``None`` on success and raises :class:`InvalidSignature` otherwise.
    Callers must treat ``payload`` as untrusted until this returns.
    """
    if not isinstance(context, Context):
        raise TypeError("context must be a Context member")
    try:
        key = load_public_key(public_key)
        key.verify(signature, payload, context=context.value)
    except (_LibInvalidSignature, ValueError) as exc:
        raise InvalidSignature(str(exc) or "signature did not verify") from exc


def verify_ok(public_key: bytes, context: Context, payload: bytes, signature: bytes) -> bool:
    """Boolean form of :func:`verify`, for tests and vector runners."""
    try:
        verify(public_key, context, payload, signature)
    except InvalidSignature:
        return False
    return True
