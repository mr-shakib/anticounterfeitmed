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

from typing import NamedTuple, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SignerUnavailable(Exception):
    """The signing service could not produce a signature."""


class GeneratedKey(NamedTuple):
    key_id: str
    public_key: bytes


class Signer(Protocol):
    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes: ...

    def generate_key(self) -> GeneratedKey: ...


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

    def generate_key(self) -> GeneratedKey:
        from medcrypto.keys import generate_keypair

        pair = generate_keypair()
        self._service.keystore.store_seed(pair.key_id, pair.private_seed)
        return GeneratedKey(key_id=pair.key_id, public_key=pair.public_key)


class RemoteSigner:
    """Calls the isolated signing service on the private network.

    The transport is mTLS, terminated by the deployment, plus a bearer token so
    that reaching the port is not the same as being allowed to sign. Failures
    raise :class:`SignerUnavailable` rather than propagating transport errors,
    because an activation run treats a signing failure as a per-unit outcome
    rather than something that aborts the job.
    """

    #: Signing is fast; a long wait here would stall an activation run rather
    #: than failing the unit and moving on.
    timeout_seconds = 10

    def __init__(self, url: str, auth_token: str = "", verify: object = True) -> None:
        if not url:
            raise ImproperlyConfigured("SIGNER_URL is required when SIGNER_MODE=service")
        if not auth_token:
            raise ImproperlyConfigured(
                "SIGNER_AUTH_TOKEN is required when SIGNER_MODE=service"
            )
        self.url = url.rstrip("/")
        self._auth_token = auth_token
        self._verify = verify

    def sign(self, *, key_id: str, context: str, payload: bytes) -> bytes:
        import base64

        import requests

        try:
            response = requests.post(
                f"{self.url}/sign",
                json={
                    "key_id": key_id,
                    "context": context,
                    "payload_b64": base64.b64encode(payload).decode("ascii"),
                },
                headers={"Authorization": f"Bearer {self._auth_token}"},
                timeout=self.timeout_seconds,
                verify=self._verify,
            )
        except requests.RequestException as exc:
            raise SignerUnavailable(f"signing service unreachable: {exc}") from exc

        if response.status_code != 200:
            # The body may name a key id but never carries key material.
            raise SignerUnavailable(
                f"signing service refused the request ({response.status_code})"
            )

        try:
            return base64.b64decode(response.json()["signature_b64"], validate=True)
        except Exception as exc:
            raise SignerUnavailable("signing service returned an unusable response") from exc

    def generate_key(self) -> GeneratedKey:
        """Ask the signing service to create a key and return its public half.

        The seed is created and kept inside that service. This process never
        sees one, which is the point of the separation.
        """
        import base64

        import requests

        try:
            response = requests.post(
                f"{self.url}/keys",
                headers={"Authorization": f"Bearer {self._auth_token}"},
                timeout=self.timeout_seconds,
                verify=self._verify,
            )
        except requests.RequestException as exc:
            raise SignerUnavailable(f"signing service unreachable: {exc}") from exc

        if response.status_code != 200:
            raise SignerUnavailable(
                f"signing service refused key generation ({response.status_code})"
            )
        body = response.json()
        return GeneratedKey(
            key_id=body["key_id"],
            public_key=base64.b64decode(body["public_key_b64"], validate=True),
        )


def get_signer() -> Signer:
    mode = getattr(settings, "SIGNER_MODE", "local")
    if mode == "service":
        return RemoteSigner(
            getattr(settings, "SIGNER_URL", ""),
            auth_token=getattr(settings, "SIGNER_AUTH_TOKEN", ""),
            verify=getattr(settings, "SIGNER_TLS_VERIFY", True),
        )
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
