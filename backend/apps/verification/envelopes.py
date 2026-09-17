"""Signed status and result envelopes.

Current status lives outside the activation credential, because a static
signature cannot know that a later scan, block or recall happened. Every
consumer response therefore carries a separately signed statement bound to the
request's nonce and to a short validity window.

What such a signature proves is narrow and worth stating plainly: it
authenticates the signing service's statement, not the correctness of every
database operation behind it.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.serialization.models import PackageUnit
from apps.trust.models import KeyPurpose
from apps.trust.services import active_key_for
from apps.trust.signing import get_signer
from medcrypto import canonicalise
from medcrypto.contexts import Context
from medcrypto.records import build_status_record


def new_nonce() -> str:
    """A fresh request nonce, echoed into the signed response."""
    return secrets.token_urlsafe(16)


@dataclass(frozen=True)
class SignedEnvelope:
    canonical_bytes: bytes
    signature: bytes
    key_id: str

    def as_response(self) -> dict:
        import base64

        return {
            "payload": base64.b64encode(self.canonical_bytes).decode("ascii"),
            "signature": base64.b64encode(self.signature).decode("ascii"),
            "key_id": self.key_id,
            "algorithm": "ML-DSA-65",
        }


def sign_status(
    *,
    unit: PackageUnit | None,
    outcome: str,
    restrictions: list[str],
    request_nonce: str,
    credential_digest: str | None = None,
    operation_id: str | None = None,
    event_id: str | None = None,
    now: datetime | None = None,
) -> SignedEnvelope:
    """Build and sign a statement of current status.

    ``unit`` is None for an unknown token: the negative answer is signed too, so
    the app can verify that "not found" genuinely came from this service rather
    than from something sitting in the middle.
    """
    now = now or timezone.now()
    key = active_key_for(purpose=KeyPurpose.STATUS)

    record = build_status_record(
        key_id=key.key_id,
        package_id=str(unit.id) if unit else "",
        token_sha256=bytes(unit.token_sha256) if unit else bytes(32),
        activation_credential_digest=credential_digest,
        lifecycle=unit.lifecycle if unit else "UNKNOWN",
        restrictions=restrictions,
        outcome=outcome,
        request_nonce=request_nonce,
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.STATUS_ENVELOPE_TTL_SECONDS),
        operation_id=operation_id,
        event_id=event_id,
    )
    payload = canonicalise(record)
    signature = get_signer().sign(
        key_id=key.key_id,
        context=Context.STATUS.value.decode(),
        payload=payload,
    )
    return SignedEnvelope(canonical_bytes=payload, signature=signature, key_id=key.key_id)
