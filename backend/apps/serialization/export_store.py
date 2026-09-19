"""Encryption for retained label exports.

A label export is the one artifact that contains raw tokens. The SRS keeps such
artifacts until a print job is reconciled and deletes them within 24 hours, so
they are held encrypted and on a clock rather than either discarded immediately
or kept forever.

What this protects against is a copy of the database: the ciphertext is useless
without the key, which lives in configuration. It does not protect against a
compromised application, which by definition can decrypt anything it is able to
serve. That is the same trade the SRS makes, and it is worth being clear about.
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class ExportUnavailable(Exception):
    """The export cannot be decrypted, or was never stored."""


def _key() -> bytes:
    """The Fernet key, from configuration.

    Falls back to one derived from SECRET_KEY so a development stack works
    without another secret to manage. Rotating either key makes existing
    exports unreadable, which is acceptable: they are short-lived by design and
    a lost export is recovered by voiding the units and reissuing.
    """
    configured = getattr(settings, "PRINT_EXPORT_KEY", "")
    if configured:
        return configured.encode() if isinstance(configured, str) else configured
    derived = hashlib.sha256(
        b"print-export:" + settings.SECRET_KEY.encode()
    ).digest()
    return base64.urlsafe_b64encode(derived)


def encrypt_export(labels: list[dict]) -> bytes:
    """Encrypt the label list for storage."""
    payload = json.dumps(labels, separators=(",", ":")).encode("utf-8")
    return Fernet(_key()).encrypt(payload)


def decrypt_export(ciphertext: bytes) -> list[dict]:
    """Recover a stored label list."""
    if not ciphertext:
        raise ExportUnavailable("no export is stored for this job")
    try:
        return json.loads(Fernet(_key()).decrypt(bytes(ciphertext)))
    except InvalidToken as exc:
        raise ExportUnavailable(
            "the stored export cannot be decrypted; the key may have changed"
        ) from exc
