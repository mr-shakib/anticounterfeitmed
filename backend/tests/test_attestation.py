"""Firebase App Check token verification.

A real App Check token can only be minted by a real Firebase project, so these
tests mint their own with a throwaway RSA key and inject a stub JWKS client.
That exercises every claim and signature check, which is the part that has to be
right. What remains untested is the wiring to a live project: that the project
number and app ids are configured correctly, which is decision D9.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.verification.attestation import AttestationFailed, FirebaseAppCheckVerifier

PROJECT_NUMBER = "123456789012"
APP_ID = "1:123456789012:android:abcdef123456"
OTHER_APP_ID = "1:123456789012:android:999999999999"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StubJWKSClient:
    """Stands in for PyJWKClient, returning one known key."""

    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        class _Key:
            key = self._key.public_key()

        return _Key()


@pytest.fixture
def verifier(signing_key):
    return FirebaseAppCheckVerifier(
        PROJECT_NUMBER, [APP_ID], jwks_client=StubJWKSClient(signing_key)
    )


def mint(signing_key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://firebaseappcheck.googleapis.com/{PROJECT_NUMBER}",
        "aud": [f"projects/{PROJECT_NUMBER}"],
        "sub": APP_ID,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    headers = overrides.pop("_headers", None) or {"typ": "JWT"}
    return jwt.encode(claims, signing_key, algorithm="RS256", headers=headers)


def test_valid_token_is_accepted(verifier, signing_key):
    assert verifier.verify(mint(signing_key)) == APP_ID


def test_expired_token_is_rejected(verifier, signing_key):
    now = int(time.time())
    token = mint(signing_key, iat=now - 7200, exp=now - 3600)
    with pytest.raises(AttestationFailed, match="rejected"):
        verifier.verify(token)


def test_wrong_issuer_is_rejected(verifier, signing_key):
    token = mint(signing_key, iss="https://firebaseappcheck.googleapis.com/999999999999")
    with pytest.raises(AttestationFailed):
        verifier.verify(token)


def test_wrong_audience_is_rejected(verifier, signing_key):
    token = mint(signing_key, aud=["projects/999999999999"])
    with pytest.raises(AttestationFailed):
        verifier.verify(token)


def test_token_for_another_app_is_rejected(verifier, signing_key):
    """The subject check is optional in Firebase's docs and mandatory here."""
    token = mint(signing_key, sub=OTHER_APP_ID)
    with pytest.raises(AttestationFailed, match="unknown app"):
        verifier.verify(token)


def test_token_signed_by_another_key_is_rejected(verifier):
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = mint(attacker_key)
    with pytest.raises(AttestationFailed):
        verifier.verify(token)


def test_unsigned_token_is_rejected(verifier):
    """The alg=none downgrade must not be accepted."""
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": f"https://firebaseappcheck.googleapis.com/{PROJECT_NUMBER}",
            "aud": [f"projects/{PROJECT_NUMBER}"],
            "sub": APP_ID,
            "exp": now + 3600,
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(AttestationFailed, match="unexpected algorithm"):
        verifier.verify(token)


def test_missing_required_claim_is_rejected(verifier, signing_key):
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": f"https://firebaseappcheck.googleapis.com/{PROJECT_NUMBER}",
            "aud": [f"projects/{PROJECT_NUMBER}"],
            "exp": now + 3600,
            # no sub
        },
        signing_key,
        algorithm="RS256",
        headers={"typ": "JWT"},
    )
    with pytest.raises(AttestationFailed):
        verifier.verify(token)


def test_empty_token_is_rejected(verifier):
    with pytest.raises(AttestationFailed, match="missing"):
        verifier.verify("")


def test_garbage_token_is_rejected(verifier):
    with pytest.raises(AttestationFailed, match="malformed"):
        verifier.verify("not-a-jwt")


def test_configuration_is_required():
    with pytest.raises(Exception):
        FirebaseAppCheckVerifier("", [APP_ID])
    with pytest.raises(Exception):
        FirebaseAppCheckVerifier(PROJECT_NUMBER, [])


def test_issuer_and_audience_are_derived_from_project_number(verifier):
    assert verifier.issuer.endswith(f"/{PROJECT_NUMBER}")
    assert verifier.audience == f"projects/{PROJECT_NUMBER}"
