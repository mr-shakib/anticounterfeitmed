"""Token, canonicalisation and binding rules."""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone

import pytest

from medcrypto import canonicalise, generate_token, hash_token, is_well_formed_token
from medcrypto.canonical import CanonicalisationError, is_canonical, parse_strict
from medcrypto.contexts import Context
from medcrypto.keys import PUBLIC_KEY_BYTES, SIGNATURE_BYTES, generate_keypair
from medcrypto.records import (
    BindingError,
    ProductSnapshot,
    build_activation_record,
    check_activation_binding,
)
from medcrypto.signing import InvalidSignature, sign, verify


def test_token_shape_and_uniqueness():
    tokens = {generate_token() for _ in range(500)}
    assert len(tokens) == 500, "tokens must not collide"
    for token in tokens:
        assert len(token) == 43
        assert is_well_formed_token(token)
        # 32 bytes of entropy survive the round trip.
        assert len(base64.urlsafe_b64decode(token + "=")) == 32


def test_hash_token_rejects_malformed_input():
    for bad in ["", "short", "!" * 43, generate_token() + "x"]:
        with pytest.raises(ValueError):
            hash_token(bad)


def test_hash_token_is_stable_and_32_bytes():
    token = generate_token()
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 32


def test_canonicalisation_is_key_order_independent():
    a = canonicalise({"b": 1, "a": 2})
    b = canonicalise({"a": 2, "b": 1})
    assert a == b
    assert is_canonical(a)


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(CanonicalisationError):
        parse_strict(b'{"a":1,"a":2}')


def test_sign_verify_roundtrip_and_sizes():
    pair = generate_keypair()
    assert len(pair.public_key) == PUBLIC_KEY_BYTES
    payload = canonicalise({"hello": "world"})
    signature = sign(pair.private_seed, Context.ACTIVATION, payload)
    assert len(signature) == SIGNATURE_BYTES
    verify(pair.public_key, Context.ACTIVATION, payload, signature)


def test_context_separation_is_enforced():
    pair = generate_keypair()
    payload = canonicalise({"hello": "world"})
    signature = sign(pair.private_seed, Context.ACTIVATION, payload)
    with pytest.raises(InvalidSignature):
        verify(pair.public_key, Context.STATUS, payload, signature)


def test_tampered_payload_fails():
    pair = generate_keypair()
    payload = canonicalise({"hello": "world"})
    signature = sign(pair.private_seed, Context.ACTIVATION, payload)
    tampered = bytearray(payload)
    tampered[0] ^= 0x01
    with pytest.raises(InvalidSignature):
        verify(pair.public_key, Context.ACTIVATION, bytes(tampered), signature)


def _record(token: str, key_id: str, manufacturer: str = "mfr-a"):
    return build_activation_record(
        key_id=key_id,
        manufacturer_id=manufacturer,
        package_id="pkg-1",
        token_sha256=hash_token(token),
        product=ProductSnapshot("Napa", "Paracetamol", "500 mg", "Tablet", "Strip of 10"),
        batch_number="BN-1",
        manufactured_on=date(2026, 1, 1),
        expires_on=date(2027, 1, 1),
        qc_event_id="qc-1",
        coating_event_id="coat-1",
        activation_approval_id="appr-1",
        activated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_binding_rejects_credential_for_another_token():
    """A genuine credential for another package must not pass binding."""
    pair = generate_keypair()
    ours, theirs = generate_token(), generate_token()
    payload = canonicalise(_record(theirs, pair.key_id))

    with pytest.raises(BindingError):
        check_activation_binding(
            payload,
            expected_token_sha256=hash_token(ours),
            expected_manufacturer_id="mfr-a",
            expected_key_id=pair.key_id,
        )


def test_binding_rejects_wrong_manufacturer_and_key():
    pair = generate_keypair()
    token = generate_token()
    payload = canonicalise(_record(token, pair.key_id, manufacturer="mfr-a"))

    with pytest.raises(BindingError):
        check_activation_binding(
            payload,
            expected_token_sha256=hash_token(token),
            expected_manufacturer_id="mfr-b",
            expected_key_id=pair.key_id,
        )
    with pytest.raises(BindingError):
        check_activation_binding(
            payload,
            expected_token_sha256=hash_token(token),
            expected_manufacturer_id="mfr-a",
            expected_key_id="mldsa65-someotherkey",
        )


def test_binding_accepts_the_matching_credential():
    pair = generate_keypair()
    token = generate_token()
    payload = canonicalise(_record(token, pair.key_id))
    record = check_activation_binding(
        payload,
        expected_token_sha256=hash_token(token),
        expected_manufacturer_id="mfr-a",
        expected_key_id=pair.key_id,
    )
    assert record["package_id"] == "pkg-1"


def test_expiry_must_follow_manufacture():
    pair = generate_keypair()
    with pytest.raises(ValueError):
        build_activation_record(
            key_id=pair.key_id,
            manufacturer_id="mfr-a",
            package_id="pkg-1",
            token_sha256=hash_token(generate_token()),
            product=ProductSnapshot("a", "b", "c", "d", "e"),
            batch_number="BN-1",
            manufactured_on=date(2027, 1, 1),
            expires_on=date(2026, 1, 1),
            qc_event_id="qc-1",
            coating_event_id="coat-1",
            activation_approval_id="appr-1",
            activated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )


def test_naive_timestamps_are_rejected():
    pair = generate_keypair()
    with pytest.raises(ValueError):
        build_activation_record(
            key_id=pair.key_id,
            manufacturer_id="mfr-a",
            package_id="pkg-1",
            token_sha256=hash_token(generate_token()),
            product=ProductSnapshot("a", "b", "c", "d", "e"),
            batch_number="BN-1",
            manufactured_on=date(2026, 1, 1),
            expires_on=date(2027, 1, 1),
            qc_event_id="qc-1",
            coating_event_id="coat-1",
            activation_approval_id="appr-1",
            activated_at=datetime(2026, 1, 2),  # no tzinfo
        )
