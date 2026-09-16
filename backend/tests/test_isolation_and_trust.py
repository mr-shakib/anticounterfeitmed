"""Cross-manufacturer isolation (milestone 2's gate) and the trust manifest."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.activation.services import ActivationNotPermitted, activate_units
from apps.organizations.models import ApprovalStatus, StaffRole
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.serialization.services import IssuanceNotPermitted, create_print_job
from apps.trust.models import KeyPurpose, KeyState, TrustManifest
from apps.trust.services import (
    NoUsableKey,
    active_key_for,
    provision_signing_key,
    publish_trust_manifest,
    revoke_key,
)
from medcrypto.canonical import parse_strict
from medcrypto.contexts import Context
from medcrypto.signing import InvalidSignature, verify
from tests.test_end_to_end import factory, take_through_manufacturing  # noqa: F401


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_activate_another_manufacturers_units(factory):
    """Milestone 2 gate: A must not be able to act on B's units."""
    org_a, membership_a, batch_a = factory("Manufacturer A")
    org_b, membership_b, batch_b = factory("Manufacturer B")

    result_b = create_print_job(batch=batch_b, count=1)
    take_through_manufacturing(result_b.units, membership_b.user)
    unit_b = PackageUnit.objects.get(pk=result_b.units[0].unit_id)

    # A's release manager attempts to activate B's unit, in B's batch.
    with pytest.raises(ActivationNotPermitted):
        activate_units(batch=batch_b, units=[unit_b], membership=membership_a)

    unit_b.refresh_from_db()
    assert unit_b.lifecycle == UnitLifecycle.COVERED, "B's unit must be untouched"


@pytest.mark.django_db(transaction=True)
def test_non_release_manager_cannot_activate(factory):
    org, membership, batch = factory()
    membership.role = StaffRole.MANUFACTURER_STAFF
    membership.save(update_fields=["role"])

    result = create_print_job(batch=batch, count=1)
    take_through_manufacturing(result.units, membership.user)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)

    with pytest.raises(ActivationNotPermitted):
        activate_units(batch=batch, units=[unit], membership=membership)


@pytest.mark.django_db(transaction=True)
def test_disabled_membership_cannot_activate(factory):
    org, membership, batch = factory()
    membership.is_enabled = False
    membership.save(update_fields=["is_enabled"])

    result = create_print_job(batch=batch, count=1)
    take_through_manufacturing(result.units, membership.user)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)

    with pytest.raises(ActivationNotPermitted):
        activate_units(batch=batch, units=[unit], membership=membership)


@pytest.mark.django_db(transaction=True)
def test_suspended_organization_cannot_issue_or_activate(factory):
    """Suspension overrides everything, including an otherwise valid role."""
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=1)
    take_through_manufacturing(result.units, membership.user)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)

    org.is_suspended = True
    org.suspended_at = timezone.now()
    org.save(update_fields=["is_suspended", "suspended_at"])
    membership.refresh_from_db()

    with pytest.raises(ActivationNotPermitted):
        activate_units(batch=batch, units=[unit], membership=membership)

    with pytest.raises(IssuanceNotPermitted):
        create_print_job(batch=batch, count=1)


@pytest.mark.django_db(transaction=True)
def test_unapproved_organization_cannot_issue(factory):
    org, membership, batch = factory()
    org.approval_status = ApprovalStatus.PENDING
    org.save(update_fields=["approval_status"])

    with pytest.raises(IssuanceNotPermitted):
        create_print_job(batch=batch, count=1)


@pytest.mark.django_db(transaction=True)
def test_each_manufacturer_signs_with_its_own_key(factory):
    org_a, membership_a, batch_a = factory("Manufacturer A")
    org_b, membership_b, batch_b = factory("Manufacturer B")

    key_a = active_key_for(purpose=KeyPurpose.ACTIVATION, organization=org_a)
    key_b = active_key_for(purpose=KeyPurpose.ACTIVATION, organization=org_b)
    assert key_a.key_id != key_b.key_id

    result = create_print_job(batch=batch_a, count=1)
    take_through_manufacturing(result.units, membership_a.user)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)
    activate_units(batch=batch_a, units=[unit], membership=membership_a)

    unit.refresh_from_db()
    credential = unit.activation_credential
    assert credential.signing_key.key_id == key_a.key_id

    # A's credential must not verify under B's key.
    with pytest.raises(InvalidSignature):
        verify(
            bytes(key_b.public_key),
            Context.ACTIVATION,
            bytes(credential.canonical_bytes),
            bytes(credential.signature),
        )


@pytest.mark.django_db(transaction=True)
def test_trust_manifest_is_signed_and_versioned(factory):
    org, membership, batch = factory()
    provision_signing_key(purpose=KeyPurpose.ROOT)
    provision_signing_key(purpose=KeyPurpose.STATUS)

    first = publish_trust_manifest()
    assert first.version == 1

    root = active_key_for(purpose=KeyPurpose.ROOT)
    verify(
        bytes(root.public_key),
        Context.TRUST_MANIFEST,
        bytes(first.canonical_bytes),
        bytes(first.signature),
    )

    record = parse_strict(bytes(first.canonical_bytes))
    assert record["schema"] == "medicine-trust-manifest-v1"
    key_ids = {entry["key_id"] for entry in record["keys"]}
    assert active_key_for(
        purpose=KeyPurpose.ACTIVATION, organization=org
    ).key_id in key_ids
    # The root key authorises the manifest; it never appears inside it.
    assert root.key_id not in key_ids

    second = publish_trust_manifest()
    assert second.version == 2, "versions must advance so rollback is detectable"


@pytest.mark.django_db(transaction=True)
def test_revoked_key_is_marked_in_the_next_manifest(factory):
    org, membership, batch = factory()
    provision_signing_key(purpose=KeyPurpose.ROOT)

    key = active_key_for(purpose=KeyPurpose.ACTIVATION, organization=org)
    revoke_key(key=key, reason="suspected compromise")

    manifest = publish_trust_manifest()
    record = parse_strict(bytes(manifest.canonical_bytes))
    entry = next(e for e in record["keys"] if e["key_id"] == key.key_id)
    assert entry["state"] == KeyState.REVOKED

    # A revoked key can no longer sign new activations.
    with pytest.raises(NoUsableKey):
        active_key_for(purpose=KeyPurpose.ACTIVATION, organization=org)
