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
    """Verifies a Firebase App Check JWT against Google's public keys.

    The token is a JWT signed by Google. Verification checks the signature
    against the JWKS, the issuer, the audience (the Firebase project), expiry,
    and that the subject is one of the app ids we published.
    """

    JWKS_URL = "https://firebaseappcheck.googleapis.com/v1/jwks"

    def __init__(self, project_number: str, allowed_app_ids: list[str]) -> None:
        if not project_number or not allowed_app_ids:
            raise ImproperlyConfigured(
                "APP_CHECK_PROJECT_NUMBER and APP_CHECK_ALLOWED_APP_IDS are "
                "required when APP_CHECK_MODE=firebase"
            )
        self.project_number = project_number
        self.allowed_app_ids = allowed_app_ids

    def verify(self, token: str) -> str:
        raise NotImplementedError(
            "Firebase App Check verification is not wired up yet. It needs a "
            "real Firebase project and Play Integrity configuration (decision "
            "D9) before it can be implemented and tested against anything real."
        )


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
