"""Consumer API tests, including the app-only access acceptance gates."""

from __future__ import annotations

import base64

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.serialization.services import create_print_job
from apps.trust.models import KeyPurpose
from apps.trust.services import provision_signing_key, publish_trust_manifest
from apps.verification.models import VerificationEvent, VerificationOutcome
from medcrypto.contexts import Context
from medcrypto.canonical import parse_strict
from medcrypto.records import check_activation_binding
from medcrypto.signing import verify
from medcrypto.tokens import hash_token
from tests.test_end_to_end import factory, take_through_manufacturing  # noqa: F401

ATTEST = {"HTTP_X_APP_CHECK": "dev-token"}


@pytest.fixture(autouse=True)
def _allow_insecure_attestation(settings):
    """Tests run with DEBUG off, so attestation must be opted into explicitly."""
    settings.APP_CHECK_MODE = "accept-any"
    settings.APP_CHECK_ALLOW_INSECURE = True


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def platform_keys(db):
    provision_signing_key(purpose=KeyPurpose.ROOT)
    provision_signing_key(purpose=KeyPurpose.STATUS)


@pytest.fixture
def active_package(factory, platform_keys):
    """An activated unit, with its raw token."""
    from apps.activation.services import activate_units

    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=1)
    take_through_manufacturing(result.units, membership.user)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)
    activate_units(batch=batch, units=[unit], membership=membership)
    unit.refresh_from_db()
    return org, unit, result.units[0].token


def make_session(client) -> str:
    response = client.post(reverse("consumer-sessions"), {}, format="json", **ATTEST)
    assert response.status_code == 201
    return response.data["session_credential"]


def auth(credential: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Session {credential}", **ATTEST}


# --- access control ---------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_attestation_required_to_create_a_session(client):
    """No attestation header, no session."""
    response = client.post(reverse("consumer-sessions"), {}, format="json")
    assert response.status_code in (401, 403)


@pytest.mark.django_db(transaction=True)
def test_prepare_requires_both_session_and_attestation(client, active_package):
    _org, _unit, token = active_package
    credential = make_session(client)
    url = reverse("consumer-prepare")
    body = {"token": token, "nonce": "n1"}

    # Neither credential.
    assert client.post(url, body, format="json").status_code in (401, 403)
    # Attestation only, no session.
    assert client.post(url, body, format="json", **ATTEST).status_code in (401, 403)
    # Session only, no attestation.
    assert client.post(
        url, body, format="json", HTTP_AUTHORIZATION=f"Session {credential}"
    ).status_code in (401, 403)
    # Both.
    assert client.post(url, body, format="json", **auth(credential)).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_invalid_session_credential_is_refused(client, active_package):
    _org, _unit, token = active_package
    response = client.post(
        reverse("consumer-prepare"),
        {"token": token, "nonce": "n"},
        format="json",
        **auth("not-a-real-credential"),
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db(transaction=True)
def test_accept_any_attestation_refused_when_not_opted_in(client, settings):
    """Production must not silently accept debug tokens.

    The misconfiguration fails closed and loudly rather than degrading to "no
    attestation": a quiet 403 could be mistaken for a client problem, while this
    names the cause.
    """
    from django.core.exceptions import ImproperlyConfigured

    settings.APP_CHECK_ALLOW_INSECURE = False
    settings.DEBUG = False

    with pytest.raises(ImproperlyConfigured, match="must not silently accept"):
        client.post(reverse("consumer-sessions"), {}, format="json", **ATTEST)


@pytest.mark.django_db(transaction=True)
def test_local_signer_refused_when_not_opted_in(settings):
    """The matching guard on in-process signing."""
    from django.core.exceptions import ImproperlyConfigured

    from apps.trust.signing import get_signer

    settings.SIGNER_ALLOW_INSECURE_LOCAL = False
    settings.DEBUG = False
    settings.SIGNER_MODE = "local"

    with pytest.raises(ImproperlyConfigured, match="not permitted outside DEBUG"):
        get_signer()


# --- the browser must never change state ------------------------------------


@pytest.mark.django_db(transaction=True)
def test_browser_style_requests_change_nothing(client, active_package):
    """GET, HEAD and unauthenticated posts must not redeem anything."""
    _org, unit, token = active_package

    for method, url in [
        ("get", reverse("consumer-prepare")),
        ("head", reverse("consumer-prepare")),
        ("get", reverse("consumer-confirm")),
        ("get", f"/#v=1&t={token}"),
    ]:
        getattr(client, method)(url)

    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.ACTIVE
    assert not VerificationEvent.objects.filter(unit=unit).exists()


# --- the flow ---------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_prepare_returns_verifiable_credential_and_does_not_redeem(client, active_package):
    org, unit, token = active_package
    credential = make_session(client)

    response = client.post(
        reverse("consumer-prepare"),
        {"token": token, "nonce": "nonce-abc"},
        format="json",
        **auth(credential),
    )
    assert response.status_code == 200
    assert response.data["outcome"] == VerificationOutcome.VERIFIED_FIRST

    # The app verifies the activation credential itself.
    cred = response.data["activation_credential"]
    key = unit.activation_credential.signing_key
    payload = base64.b64decode(cred["payload"])
    verify(bytes(key.public_key), Context.ACTIVATION, payload, base64.b64decode(cred["signature"]))
    check_activation_binding(
        payload,
        expected_token_sha256=hash_token(token),
        expected_manufacturer_id=str(org.id),
        expected_key_id=key.key_id,
    )

    # And the status envelope, which must echo the nonce it was given.
    from apps.trust.services import active_key_for

    status_key = active_key_for(purpose=KeyPurpose.STATUS)
    env = response.data["status"]
    env_payload = base64.b64decode(env["payload"])
    verify(
        bytes(status_key.public_key),
        Context.STATUS,
        env_payload,
        base64.b64decode(env["signature"]),
    )
    record = parse_strict(env_payload)
    assert record["request_nonce"] == "nonce-abc"
    assert record["outcome"] == VerificationOutcome.VERIFIED_FIRST

    # Previewing redeems nothing.
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.ACTIVE


@pytest.mark.django_db(transaction=True)
def test_confirm_commits_once_and_replays_on_retry(client, active_package):
    _org, unit, token = active_package
    credential = make_session(client)

    prepared = client.post(
        reverse("consumer-prepare"),
        {"token": token, "nonce": "n1"},
        format="json",
        **auth(credential),
    ).data

    body = {
        "unit_id": prepared["unit_id"],
        "challenge_id": prepared["challenge_id"],
        "idempotency_key": "idem-1",
        "nonce": "n2",
    }
    first = client.post(reverse("consumer-confirm"), body, format="json", **auth(credential))
    assert first.status_code == 200
    assert first.data["first_verification_recorded"] is True

    # An exact retry returns the same operation without a second event.
    again = client.post(reverse("consumer-confirm"), body, format="json", **auth(credential))
    assert again.status_code == 200
    assert again.data["operation_id"] == first.data["operation_id"]
    assert again.data["replayed"] is True
    assert VerificationEvent.objects.filter(unit=unit).count() == 1


@pytest.mark.django_db(transaction=True)
def test_unknown_token_gets_a_signed_negative_answer(client, platform_keys):
    """A negative answer is signed too, so the app can verify it."""
    from medcrypto import generate_token

    credential = make_session(client)
    response = client.post(
        reverse("consumer-prepare"),
        {"token": generate_token(), "nonce": "n"},
        format="json",
        **auth(credential),
    )
    assert response.status_code == 200
    assert response.data["outcome"] == VerificationOutcome.NOT_FOUND
    assert response.data["activation_credential"] is None

    from apps.trust.services import active_key_for

    key = active_key_for(purpose=KeyPurpose.STATUS)
    env = response.data["status"]
    verify(
        bytes(key.public_key),
        Context.STATUS,
        base64.b64decode(env["payload"]),
        base64.b64decode(env["signature"]),
    )


@pytest.mark.django_db(transaction=True)
def test_operation_status_is_scoped_to_its_own_session(client, active_package):
    """One installation must not read another's operations."""
    _org, _unit, token = active_package
    mine = make_session(client)
    theirs = make_session(client)

    prepared = client.post(
        reverse("consumer-prepare"), {"token": token, "nonce": "n"},
        format="json", **auth(mine),
    ).data
    confirmed = client.post(
        reverse("consumer-confirm"),
        {
            "unit_id": prepared["unit_id"],
            "challenge_id": prepared["challenge_id"],
            "idempotency_key": "k",
            "nonce": "n2",
        },
        format="json",
        **auth(mine),
    ).data

    url = reverse("consumer-operation-status", args=[confirmed["operation_id"]])
    assert client.post(url, {"nonce": "n3"}, format="json", **auth(mine)).status_code == 200
    assert client.post(url, {"nonce": "n3"}, format="json", **auth(theirs)).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_trust_manifest_is_served_and_verifiable(client, factory, platform_keys):
    publish_trust_manifest()
    response = client.get(reverse("trust-manifest"))
    assert response.status_code == 200

    from apps.trust.services import active_key_for

    root = active_key_for(purpose=KeyPurpose.ROOT)
    verify(
        bytes(root.public_key),
        Context.TRUST_MANIFEST,
        base64.b64decode(response.data["payload"]),
        base64.b64decode(response.data["signature"]),
    )
    assert response.data["version"] == 1


@pytest.mark.django_db(transaction=True)
def test_report_accepts_an_external_reference_without_a_token(client, platform_keys):
    credential = make_session(client)
    response = client.post(
        reverse("consumer-reports"),
        {
            "reason": "SCAN_FAILED",
            "description": "The code will not scan after scratching.",
            "external_reference": "BN-2026-0042-000123",
        },
        format="json",
        **auth(credential),
    )
    assert response.status_code == 201
    assert response.data["case_number"].startswith("CASE-")


@pytest.mark.django_db(transaction=True)
def test_prepare_is_rate_limited_per_session(client, active_package, monkeypatch):
    """The limit applies per session, and a throttled request changes nothing.

    The rate is patched on the throttle class rather than through settings:
    DRF binds THROTTLE_RATES as a class attribute at import time, so a settings
    override does not reach it once the class has been imported.
    """
    from django.core.cache import cache

    from apps.verification.throttling import PrepareThrottle

    monkeypatch.setattr(
        PrepareThrottle, "THROTTLE_RATES", {"consumer_prepare": "3/min"}, raising=False
    )
    cache.clear()

    _org, unit, token = active_package
    credential = make_session(client)
    url = reverse("consumer-prepare")
    body = {"token": token, "nonce": "n"}

    codes = [
        client.post(url, body, format="json", **auth(credential)).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [200, 200, 200], f"first three should pass, got {codes}"
    assert 429 in codes, f"expected throttling, got {codes}"

    # A second session has its own allowance.
    other = make_session(client)
    assert client.post(url, body, format="json", **auth(other)).status_code == 200

    # Throttling never changes unit state.
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.ACTIVE
    cache.clear()
