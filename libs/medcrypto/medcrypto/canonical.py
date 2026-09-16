"""RFC 8785 (JCS) canonicalisation and strict JSON parsing.

Signed bytes must be reproducible byte-for-byte across Python, Dart and any
cross-check implementation, so every record is canonicalised before signing and
the *received bytes* -- not a re-serialisation of them -- are what gets verified.

``parse_strict`` exists because ``json.loads`` silently keeps the last value for
a duplicate key. A payload containing a key twice is ambiguous and is rejected
rather than interpreted.
"""

from __future__ import annotations

import json
from typing import Any

import rfc8785


class CanonicalisationError(ValueError):
    """Raised when a record cannot be canonicalised or parsed unambiguously."""


def canonicalise(record: Any) -> bytes:
    """Return the RFC 8785 canonical encoding of ``record``.

    The result is what gets signed and transmitted. Callers must send these
    exact bytes rather than re-serialising the parsed structure.
    """
    try:
        return rfc8785.dumps(record)
    except Exception as exc:  # rfc8785 raises several types for invalid input
        raise CanonicalisationError(f"cannot canonicalise record: {exc}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise CanonicalisationError(f"duplicate JSON key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_strict(payload: bytes) -> Any:
    """Parse JSON, rejecting duplicate keys.

    Use this for every payload that arrives from outside, including payloads
    whose signature has already been verified -- a valid signature over
    ambiguous JSON is still ambiguous.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonicalisationError("payload is not valid UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except CanonicalisationError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalisationError(f"payload is not valid JSON: {exc}") from exc


def is_canonical(payload: bytes) -> bool:
    """True when ``payload`` is already in canonical form.

    Useful as an assertion on bytes we are about to store: it catches a caller
    that signed a re-serialised structure instead of the canonical encoding.
    """
    try:
        return canonicalise(parse_strict(payload)) == payload
    except CanonicalisationError:
        return False
