"""ML-DSA context strings.

Context strings are the domain separator required by docs/06. A signature
produced for one context must fail verification under another; the library
enforces this, so these constants are the entire mechanism. Never sign with an
empty context, and never reuse a context for a new record shape -- add a new
versioned member instead.
"""

from __future__ import annotations

import enum


class Context(bytes, enum.Enum):
    """Permitted ML-DSA context strings, one per signed record type."""

    ACTIVATION = b"medicine-activation-v1"
    STATUS = b"medicine-status-v1"
    TRUST_MANIFEST = b"medicine-trust-manifest-v1"

    def __str__(self) -> str:  # pragma: no cover - debugging affordance
        return self.value.decode("ascii")
