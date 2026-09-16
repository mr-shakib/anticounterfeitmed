#!/usr/bin/env python
"""Regenerate the golden signature vectors.

Run this only when a record schema or context string changes. The generated
files are committed and become the contract every implementation must satisfy:
the Django backend, the signing service, the Dart client and the OpenSSL CLI
cross-check all run the same vectors.

Key seeds are fixed so public keys stay stable across regenerations. ML-DSA
signing is randomised, so signature bytes will differ each run -- that is
expected, and is why the generated files are committed rather than rebuilt in CI.
"""

from __future__ import annotations

import base64
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from medcrypto import canonicalise, hash_token
from medcrypto.contexts import Context
from medcrypto.keys import generate_keypair, key_id_for_public_key, load_private_key
from medcrypto.records import (
    ProductSnapshot,
    build_activation_record,
    build_status_record,
    credential_digest,
)
from medcrypto.signing import sign

HERE = Path(__file__).parent

# Fixed seeds: stable public keys and key ids across regenerations.
MANUFACTURER_SEED = bytes(range(32))
OTHER_MANUFACTURER_SEED = bytes(range(100, 132))
SERVICE_SEED = bytes(range(200, 232))

# Fixed tokens derived from constant bytes, so vectors stay reproducible.
TOKEN = base64.urlsafe_b64encode(bytes((i * 7 + 11) % 256 for i in range(32))).rstrip(b"=").decode()
OTHER_TOKEN = base64.urlsafe_b64encode(bytes((i * 13 + 29) % 256 for i in range(32))).rstrip(b"=").decode()

ACTIVATED_AT = datetime(2026, 3, 1, 9, 30, 0, tzinfo=timezone.utc)
ISSUED_AT = datetime(2026, 3, 2, 14, 0, 0, tzinfo=timezone.utc)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def public_of(seed: bytes) -> bytes:
    return load_private_key(seed).public_key().public_bytes_raw()


def write_vector(folder: str, name: str, vector: dict) -> None:
    path = HERE / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.json").write_text(json.dumps(vector, indent=2) + "\n")


def make_activation_payload(seed: bytes, token: str) -> tuple[bytes, str]:
    public = public_of(seed)
    key_id = key_id_for_public_key(public)
    record = build_activation_record(
        key_id=key_id,
        manufacturer_id="mfr-square-pharmaceuticals",
        package_id="pkg-0000000000000001",
        token_sha256=hash_token(token),
        product=ProductSnapshot(
            brand="Napa",
            generic="Paracetamol",
            strength="500 mg",
            dosage_form="Tablet",
            pack_description="Strip of 10 tablets",
        ),
        batch_number="BN-2026-0042",
        manufactured_on=date(2026, 2, 1),
        expires_on=date(2028, 1, 31),
        qc_event_id="qc-evt-0001",
        coating_event_id="coat-evt-0001",
        activation_approval_id="appr-0001",
        activated_at=ACTIVATED_AT,
    )
    return canonicalise(record), key_id


def main() -> None:
    for folder in ("activation", "status", "negative"):
        shutil.rmtree(HERE / folder, ignore_errors=True)

    manufacturer_public = public_of(MANUFACTURER_SEED)
    other_public = public_of(OTHER_MANUFACTURER_SEED)
    service_public = public_of(SERVICE_SEED)

    # --- valid activation credential -------------------------------------
    payload, key_id = make_activation_payload(MANUFACTURER_SEED, TOKEN)
    signature = sign(MANUFACTURER_SEED, Context.ACTIVATION, payload)
    write_vector(
        "activation",
        "valid-activation",
        {
            "name": "valid-activation",
            "description": "Correctly signed activation credential for the reference unit.",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(manufacturer_public),
            "key_id": key_id,
            "payload": b64(payload),
            "signature": b64(signature),
            "token": TOKEN,
            "token_sha256": hash_token(TOKEN).hex(),
            "expected": "VALID",
        },
    )

    # --- valid status envelope -------------------------------------------
    service_key_id = key_id_for_public_key(service_public)
    status_record = build_status_record(
        key_id=service_key_id,
        package_id="pkg-0000000000000001",
        token_sha256=hash_token(TOKEN),
        activation_credential_digest=credential_digest(payload),
        lifecycle="REDEEMED",
        restrictions=[],
        outcome="VERIFIED_FIRST",
        request_nonce="s5Xq2n0mQb6vT1kYpL8wZg",
        issued_at=ISSUED_AT,
        expires_at=ISSUED_AT + timedelta(seconds=120),
        operation_id="op-0001",
        event_id="evt-0001",
    )
    status_payload = canonicalise(status_record)
    status_signature = sign(SERVICE_SEED, Context.STATUS, status_payload)
    write_vector(
        "status",
        "valid-status",
        {
            "name": "valid-status",
            "description": "Correctly signed status envelope committing a first verification.",
            "context": Context.STATUS.value.decode(),
            "public_key": b64(service_public),
            "key_id": service_key_id,
            "payload": b64(status_payload),
            "signature": b64(status_signature),
            "expected": "VALID",
        },
    )

    # --- negative vectors -------------------------------------------------
    tampered = bytearray(payload)
    tampered[len(tampered) // 2] ^= 0x01
    negatives = [
        {
            "name": "tampered-payload",
            "description": "One byte of the canonical payload flipped after signing.",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(manufacturer_public),
            "payload": b64(bytes(tampered)),
            "signature": b64(signature),
            "expected": "INVALID",
            "reason": "payload does not match the signature",
        },
        {
            "name": "wrong-context",
            "description": "Activation signature presented under the status context.",
            "context": Context.STATUS.value.decode(),
            "public_key": b64(manufacturer_public),
            "payload": b64(payload),
            "signature": b64(signature),
            "expected": "INVALID",
            "reason": "context separation must reject cross-context reuse",
        },
        {
            "name": "wrong-key",
            "description": "Valid signature checked against another manufacturer's key.",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(other_public),
            "payload": b64(payload),
            "signature": b64(signature),
            "expected": "INVALID",
            "reason": "signature was not made by this key",
        },
        {
            "name": "truncated-signature",
            "description": "Final byte removed from an otherwise valid signature.",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(manufacturer_public),
            "payload": b64(payload),
            "signature": b64(signature[:-1]),
            "expected": "INVALID",
            "reason": "signature length must be exactly 3309 bytes",
        },
        {
            "name": "empty-signature",
            "description": "Zero-length signature.",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(manufacturer_public),
            "payload": b64(payload),
            "signature": "",
            "expected": "INVALID",
            "reason": "a missing signature must never verify",
        },
    ]
    for vector in negatives:
        write_vector("negative", vector["name"], vector)

    # Duplicate-key and wrong-binding vectors are parser/binding concerns
    # rather than signature concerns, so they carry their own shape.
    dup = b'{"schema":"medicine-activation-v1","schema":"other"}'
    write_vector(
        "negative",
        "duplicate-json-key",
        {
            "name": "duplicate-json-key",
            "description": "Payload repeats a JSON key; parsing must refuse it.",
            "check": "parse",
            "payload": b64(dup),
            "expected": "INVALID",
            "reason": "duplicate keys make the record ambiguous",
        },
    )

    other_payload, _ = make_activation_payload(MANUFACTURER_SEED, OTHER_TOKEN)
    other_signature = sign(MANUFACTURER_SEED, Context.ACTIVATION, other_payload)
    write_vector(
        "negative",
        "wrong-token-binding",
        {
            "name": "wrong-token-binding",
            "description": (
                "A genuinely signed credential for a different package, presented "
                "alongside this unit's token. The signature verifies; the binding "
                "check must still reject it."
            ),
            "check": "binding",
            "context": Context.ACTIVATION.value.decode(),
            "public_key": b64(manufacturer_public),
            "key_id": key_id,
            "payload": b64(other_payload),
            "signature": b64(other_signature),
            "presented_with_token": TOKEN,
            "expected": "INVALID",
            "reason": "credential is bound to a different token",
        },
    )

    print("vectors written to", HERE)


if __name__ == "__main__":
    main()
