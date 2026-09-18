"""Signing key provisioning and the trust manifest.

Note on custody: in this pilot the platform provisions and holds manufacturer
keys, so what the system produces is a *platform-managed manufacturer-associated
signature* -- not independent proof that only the manufacturer could sign. That
wording is required in reports and user-facing claims. Independent custody needs
manufacturer-operated signing infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.organizations.models import Organization
from apps.trust.models import KeyPurpose, KeyState, SigningKey, TrustManifest
from apps.trust.signing import get_signer
from medcrypto import canonicalise
from medcrypto.contexts import Context


class NoUsableKey(Exception):
    """No active signing key exists for this purpose."""


@transaction.atomic
def provision_signing_key(
    *,
    purpose: str,
    organization: Organization | None = None,
    valid_from: datetime | None = None,
) -> SigningKey:
    """Generate a key pair, hand the seed to the signer, keep only the public key.

    Generation happens inside the signing service in every mode, so no private
    seed ever exists in this process. What is recorded here is the public key
    and a reference to where the seed lives.
    """
    if purpose == KeyPurpose.ACTIVATION and organization is None:
        raise ValueError("activation keys must belong to a manufacturer")

    # Generated inside the signing service, which keeps the private seed. This
    # process records only the public half and a reference; it never holds key
    # material, in any mode.
    generated = get_signer().generate_key()

    key = SigningKey.objects.create(
        key_id=generated.key_id,
        purpose=purpose,
        organization=organization,
        public_key=generated.public_key,
        private_key_reference=f"keystore:{generated.key_id}",
        state=KeyState.ACTIVE,
        valid_from=valid_from or timezone.now(),
    )
    return key


def active_key_for(*, purpose: str, organization: Organization | None = None) -> SigningKey:
    now = timezone.now()
    query = SigningKey.objects.filter(purpose=purpose, state=KeyState.ACTIVE)
    query = query.filter(organization=organization) if organization else query.filter(
        organization__isnull=True
    )
    for key in query.order_by("-valid_from"):
        if key.is_usable_for_signing(now):
            return key
    raise NoUsableKey(f"no usable {purpose} key")


@transaction.atomic
def revoke_key(*, key: SigningKey, reason: str) -> SigningKey:
    """Revoke a key and record why.

    Revocation does not retroactively invalidate history by itself: credentials
    signed by a revoked key trigger a verification hold and human review rather
    than being silently trusted or silently discarded.
    """
    key.state = KeyState.REVOKED
    key.revoked_at = timezone.now()
    key.revocation_reason = reason
    key.save(update_fields=["state", "revoked_at", "revocation_reason"])

    AuditEvent.objects.create(
        action=AuditAction.KEY_REVOKED,
        organization=key.organization,
        reason=reason,
        detail={"key_id": key.key_id, "purpose": key.purpose},
    )
    return key


def build_manifest_record(*, version: int, issued_at: datetime) -> dict:
    """Assemble the list of keys clients may trust."""
    entries = []
    for key in SigningKey.objects.exclude(purpose=KeyPurpose.ROOT).order_by("key_id"):
        entries.append(
            {
                "key_id": key.key_id,
                "algorithm": key.algorithm,
                "purpose": key.purpose,
                "organization_id": str(key.organization_id) if key.organization_id else None,
                "public_key": bytes(key.public_key).hex(),
                "state": key.state,
                "valid_from": key.valid_from.astimezone(dt_timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "valid_until": (
                    key.valid_until.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if key.valid_until
                    else None
                ),
            }
        )
    return {
        "schema": "medicine-trust-manifest-v1",
        "version": version,
        "issued_at": issued_at.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "keys": entries,
    }


@transaction.atomic
def publish_trust_manifest() -> TrustManifest:
    """Sign and store the next manifest version.

    Versions only ever increase. An installation that has seen version N refuses
    anything older, so a revoked key cannot be restored by replaying an old
    manifest.
    """
    root = active_key_for(purpose=KeyPurpose.ROOT)
    latest = TrustManifest.objects.order_by("-version").first()
    version = (latest.version + 1) if latest else 1

    issued_at = timezone.now()
    record = build_manifest_record(version=version, issued_at=issued_at)
    payload = canonicalise(record)

    signature = get_signer().sign(
        key_id=root.key_id,
        context=Context.TRUST_MANIFEST.value.decode(),
        payload=payload,
    )

    return TrustManifest.objects.create(
        version=version,
        canonical_bytes=payload,
        signature=signature,
        signed_by=root,
        issued_at=issued_at,
    )
