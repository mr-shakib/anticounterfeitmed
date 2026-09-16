"""Builders and validators for the two signed record types.

These functions build the *record structure* only. They do not decide whether a
unit may be activated or what a verification outcome should be -- that is the
backend's job. Keeping schema construction here means the app, the signer and
the test vectors cannot drift apart.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from medcrypto.canonical import CanonicalisationError, canonicalise, parse_strict
from medcrypto.keys import ALGORITHM
from medcrypto.tokens import digests_equal

ACTIVATION_SCHEMA = "medicine-activation-v1"
STATUS_SCHEMA = "medicine-status-v1"


def _utc_iso(value: datetime) -> str:
    """Render a timestamp as a UTC ISO-8601 string with a trailing Z."""
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_date(value: date) -> str:
    return value.isoformat()


@dataclass(frozen=True)
class ProductSnapshot:
    """The frozen product description embedded in an activation credential.

    Once signed this can never change; a correction means blocking and replacing
    the unit, not editing the record.
    """

    brand: str
    generic: str
    strength: str
    dosage_form: str
    pack_description: str

    def as_record(self) -> dict[str, str]:
        return {
            "brand": self.brand,
            "generic": self.generic,
            "strength": self.strength,
            "dosage_form": self.dosage_form,
            "pack_description": self.pack_description,
        }


def build_activation_record(
    *,
    key_id: str,
    manufacturer_id: str,
    package_id: str,
    token_sha256: bytes,
    product: ProductSnapshot,
    batch_number: str,
    manufactured_on: date,
    expires_on: date,
    qc_event_id: str,
    coating_event_id: str,
    activation_approval_id: str,
    activated_at: datetime,
    record_version: int = 1,
) -> dict[str, Any]:
    """Build the immutable per-unit activation credential record."""
    if expires_on <= manufactured_on:
        raise ValueError("expires_on must be after manufactured_on")
    if len(token_sha256) != 32:
        raise ValueError("token_sha256 must be a 32-byte digest")
    return {
        "schema": ACTIVATION_SCHEMA,
        "algorithm": ALGORITHM,
        "key_id": key_id,
        "manufacturer_id": manufacturer_id,
        "package_id": package_id,
        "token_sha256": token_sha256.hex(),
        "product_snapshot": product.as_record(),
        "batch_number": batch_number,
        "manufactured_on": _iso_date(manufactured_on),
        "expires_on": _iso_date(expires_on),
        "qc_event_id": qc_event_id,
        "coating_event_id": coating_event_id,
        "activation_approval_id": activation_approval_id,
        "activated_at": _utc_iso(activated_at),
        "record_version": record_version,
    }


def credential_digest(canonical_credential: bytes) -> str:
    """SHA-256 over the canonical credential bytes, as hex.

    Status envelopes carry this so a status statement is bound to the exact
    credential version the app previewed.
    """
    return hashlib.sha256(canonical_credential).hexdigest()


def build_status_record(
    *,
    key_id: str,
    package_id: str,
    token_sha256: bytes,
    activation_credential_digest: str | None,
    lifecycle: str,
    restrictions: list[str],
    outcome: str,
    request_nonce: str,
    issued_at: datetime,
    expires_at: datetime,
    operation_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build a short-lived signed statement of current status.

    Status lives outside the activation credential because a static signature
    cannot know that a later scan, block or recall happened.
    """
    if expires_at <= issued_at:
        raise ValueError("expires_at must be after issued_at")
    if len(token_sha256) != 32:
        raise ValueError("token_sha256 must be a 32-byte digest")
    if not request_nonce:
        raise ValueError("request_nonce is required for replay binding")
    return {
        "schema": STATUS_SCHEMA,
        "algorithm": ALGORITHM,
        "key_id": key_id,
        "package_id": package_id,
        "token_sha256": token_sha256.hex(),
        "activation_credential_digest": activation_credential_digest,
        "lifecycle": lifecycle,
        "restrictions": sorted(restrictions),
        "outcome": outcome,
        "operation_id": operation_id,
        "event_id": event_id,
        "request_nonce": request_nonce,
        "issued_at": _utc_iso(issued_at),
        "expires_at": _utc_iso(expires_at),
    }


class BindingError(Exception):
    """Raised when a record's signature is valid but it describes another unit."""


def check_activation_binding(
    canonical_credential: bytes,
    *,
    expected_token_sha256: bytes,
    expected_manufacturer_id: str,
    expected_key_id: str,
) -> dict[str, Any]:
    """Confirm a verified credential actually belongs here, then return it.

    A valid signature is not sufficient. A genuine credential for a *different*
    package, presented alongside this token, must be rejected -- so the token
    commitment, the issuing manufacturer and the key are all checked.

    Call this only after the signature has verified.
    """
    record = parse_strict(canonical_credential)
    if not isinstance(record, dict):
        raise BindingError("credential is not a JSON object")
    if record.get("schema") != ACTIVATION_SCHEMA:
        raise BindingError("unexpected credential schema")
    if record.get("algorithm") != ALGORITHM:
        raise BindingError("unexpected credential algorithm")

    token_hex = record.get("token_sha256")
    if not isinstance(token_hex, str):
        raise BindingError("credential has no token commitment")
    try:
        token_digest = bytes.fromhex(token_hex)
    except ValueError as exc:
        raise BindingError("token commitment is not hex") from exc
    if not digests_equal(token_digest, expected_token_sha256):
        raise BindingError("credential is bound to a different token")

    if record.get("manufacturer_id") != expected_manufacturer_id:
        raise BindingError("credential issued by a different manufacturer")
    if record.get("key_id") != expected_key_id:
        raise BindingError("credential signed by an unexpected key")
    return record


__all__ = [
    "ACTIVATION_SCHEMA",
    "STATUS_SCHEMA",
    "ProductSnapshot",
    "BindingError",
    "build_activation_record",
    "build_status_record",
    "credential_digest",
    "check_activation_binding",
    "canonicalise",
    "CanonicalisationError",
]
