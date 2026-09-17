"""App attestation.

Consumer endpoints require a valid Firebase App Check token in addition to a
session credential. Attestation says something about the *app*; the session says
something about the installation. Neither substitutes for the other, and neither
identifies a person.

App Check reduces abuse. It cannot make a copied QR undecodable, and it cannot
stop someone using the genuine app with a copied token.
"""

from __future__ import annotations

from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AttestationFailed(Exception):
    """The request did not carry acceptable app attestation."""


class AttestationVerifier(Protocol):
    def verify(self, token: str) -> str: ...


class AcceptAnyVerifier:
    """Development only. Accepts any non-empty token and returns a fixed app id.

    Refused outside DEBUG unless explicitly opted into, because silently
    accepting debug tokens in production would remove the control entirely.
    """

    def verify(self, token: str) -> str:
        if not token:
            raise AttestationFailed("missing attestation token")
        return "dev.app"


class FirebaseAppCheckVerifier:
    """Verifies a Firebase App Check token on our own backend.

    The token is a JWT signed by Google. Verification is offline against the
    cached JWKS, so a scan costs no round trip to Google and adds nothing to the
    latency budget.

    Checks performed, per Firebase's custom-backend guidance:

    * header ``alg`` is RS256 and ``typ`` is JWT;
    * signature verifies against the JWKS key named by ``kid``;
    * ``iss`` is ``https://firebaseappcheck.googleapis.com/<project_number>``;
    * ``aud`` contains ``projects/<project_number>``;
    * ``exp`` has not passed;
    * ``sub`` is one of the app ids we published.

    The ``sub`` check is optional in Firebase's documentation. It is mandatory
    here: without it any App Check token from any app in the project would be
    accepted, which is not the control we want.
    """

    JWKS_URL = "https://firebaseappcheck.googleapis.com/v1/jwks"
    ALGORITHM = "RS256"
    LEEWAY_SECONDS = 30

    def __init__(
        self,
        project_number: str,
        allowed_app_ids: list[str],
        jwks_client=None,
    ) -> None:
        if not project_number or not allowed_app_ids:
            raise ImproperlyConfigured(
                "APP_CHECK_PROJECT_NUMBER and APP_CHECK_ALLOWED_APP_IDS are "
                "required when APP_CHECK_MODE=firebase"
            )
        self.project_number = str(project_number)
        self.allowed_app_ids = set(allowed_app_ids)
        self._jwks_client = jwks_client

    @property
    def issuer(self) -> str:
        return f"https://firebaseappcheck.googleapis.com/{self.project_number}"

    @property
    def audience(self) -> str:
        return f"projects/{self.project_number}"

    def _client(self):
        # Built lazily and cached on the instance: PyJWKClient caches fetched
        # keys, so key rotation is picked up without a request per scan.
        if self._jwks_client is None:
            from jwt import PyJWKClient

            self._jwks_client = PyJWKClient(self.JWKS_URL, cache_keys=True)
        return self._jwks_client

    def verify(self, token: str) -> str:
        import jwt

        if not token:
            raise AttestationFailed("missing attestation token")

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AttestationFailed(f"malformed attestation token: {exc}") from exc

        if header.get("alg") != self.ALGORITHM:
            raise AttestationFailed(f"unexpected algorithm {header.get('alg')!r}")
        if header.get("typ") not in ("JWT", "jwt"):
            raise AttestationFailed(f"unexpected token type {header.get('typ')!r}")

        try:
            signing_key = self._client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[self.ALGORITHM],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AttestationFailed(f"attestation token rejected: {exc}") from exc
        except Exception as exc:  # JWKS fetch failures surface here
            raise AttestationFailed(f"could not verify attestation: {exc}") from exc

        app_id = claims.get("sub", "")
        if app_id not in self.allowed_app_ids:
            raise AttestationFailed("attestation token is for an unknown app")
        return app_id


def get_attestation_verifier() -> AttestationVerifier:
    mode = getattr(settings, "APP_CHECK_MODE", "accept-any")
    if mode == "firebase":
        return FirebaseAppCheckVerifier(
            getattr(settings, "APP_CHECK_PROJECT_NUMBER", ""),
            list(getattr(settings, "APP_CHECK_ALLOWED_APP_IDS", [])),
        )
    if mode == "accept-any":
        allowed = settings.DEBUG or getattr(settings, "APP_CHECK_ALLOW_INSECURE", False)
        if not allowed:
            raise ImproperlyConfigured(
                "APP_CHECK_MODE=accept-any performs no attestation and is not "
                "permitted outside DEBUG. Production must not silently accept "
                "debug tokens."
            )
        return AcceptAnyVerifier()
    raise ImproperlyConfigured(f"unknown APP_CHECK_MODE: {mode!r}")
