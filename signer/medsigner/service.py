"""The signing operation itself."""

from __future__ import annotations

from medcrypto.contexts import Context
from medcrypto.signing import sign as _sign
from medsigner.keystore import KeyStore

#: Contexts this service will sign under. An unrecognised context is refused
#: rather than passed through, so a caller cannot invent a new record type and
#: have it signed by an existing key.
PERMITTED_CONTEXTS = {member.value.decode(): member for member in Context}


class UnknownContext(Exception):
    """The requested context string is not one this service signs under."""


class SigningService:
    def __init__(self, keystore: KeyStore) -> None:
        self._keystore = keystore

    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes:
        """Sign ``payload`` with ``key_id`` under ``context``.

        ``payload`` is treated as opaque. This service does not parse it, and
        does not check that it says what the caller believes it says -- that
        binding is the backend's responsibility and is re-checked on the client.
        """
        member = PERMITTED_CONTEXTS.get(context)
        if member is None:
            raise UnknownContext(f"refusing to sign under context {context!r}")
        if not payload:
            raise ValueError("refusing to sign an empty payload")

        seed = self._keystore.load_seed(key_id)
        try:
            return _sign(seed, member, payload)
        finally:
            # Drop the reference promptly. Python gives no guarantee the bytes
            # are erased, so this is hygiene rather than a security control --
            # the real control is that the seed never leaves this process.
            del seed
