"""The isolated signing component (package `medsigner`).

This package holds ML-DSA private keys and does exactly one thing with them:
sign bytes it is handed. It has no database credentials, no object storage
access and no public route.

It deliberately does not build the records it signs and does not interpret them
semantically. The caller supplies finished canonical bytes; the signer supplies
a signature. That keeps the blast radius of a compromised application process
to "can request signatures", which is audited, rather than "can read a key".
"""

from medsigner.keystore import KeyNotAvailable, KeyStore
from medsigner.service import SigningService, UnknownContext

__all__ = ["KeyStore", "KeyNotAvailable", "SigningService", "UnknownContext"]
