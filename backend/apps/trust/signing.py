"""The backend's boundary to the signing service.

The backend never loads a private key. It asks for a signature through this
interface and receives bytes back. Two implementations exist:

* ``LocalSigner`` runs the signing code in this process, for development and
  tests. It is refused when DEBUG is off, so a deployment cannot fall into it
  by leaving a setting unset.
* ``RemoteSigner`` calls the isolated service over the private network. That is
  what staging and pilot use.

Keeping both behind one interface means the isolation boundary is a deployment
decision rather than a code change.
"""

from __future__ import annotations

from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SignerUnavailable(Exception):
    """The signing service could not produce a signature."""


class Signer(Protocol):
    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes: ...


class LocalSigner:
    """In-process signing. Development and tests only."""

    def __init__(self, keystore_path: str) -> None:
        from medsigner import KeyStore, SigningService

        self._service = SigningService(KeyStore(keystore_path))

    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes:
        from medsigner import KeyNotAvailable, UnknownContext

        try:
            return self._service.sign(key_id=key_id, context=context, payload=payload)
        except (KeyNotAvailable, UnknownContext) as exc:
            raise SignerUnavailable(str(exc)) from exc


class RemoteSigner:
    """Calls the isolated signing service over mTLS on the private network."""

    def __init__(self, url: str) -> None:
        if not url:
            raise ImproperlyConfigured("SIGNER_URL is required when SIGNER_MODE=service")
        self.url = url.rstrip("/")

    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes:
        raise NotImplementedError(
            "The signing service transport is not implemented yet. "
            "Deploying with SIGNER_MODE=service requires it; see docs/02."
        )


def get_signer() -> Signer:
    mode = getattr(settings, "SIGNER_MODE", "local")
    if mode == "service":
        return RemoteSigner(getattr(settings, "SIGNER_URL", ""))
    if mode == "local":
        allowed = settings.DEBUG or getattr(settings, "SIGNER_ALLOW_INSECURE_LOCAL", False)
        if not allowed:
            raise ImproperlyConfigured(
                "SIGNER_MODE=local signs inside the application process and is "
                "not permitted outside DEBUG. Point SIGNER_URL at the isolated "
                "signing service."
            )
        return LocalSigner(settings.SIGNER_KEYSTORE_PATH)
    raise ImproperlyConfigured(f"unknown SIGNER_MODE: {mode!r}")
