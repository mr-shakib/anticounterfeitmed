"""Signing keys and the root-signed trust manifest.

This table holds public key material and a *reference* to where the private key
lives. Private keys themselves never reach the database -- only the signing
service can load them.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.organizations.models import Organization


class KeyPurpose(models.TextChoices):
    ACTIVATION = "ACTIVATION", "Manufacturer activation credentials"
    STATUS = "STATUS", "Platform status and receipt envelopes"
    ROOT = "ROOT", "Offline root, authorises the manifest"


class KeyState(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired, still valid for historical credentials"
    REVOKED = "REVOKED", "Revoked, triggers a verification hold"


class SigningKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: Derived from the public key, so an id cannot be repointed at other material.
    key_id = models.CharField(max_length=80, unique=True)
    algorithm = models.CharField(max_length=20, default="ML-DSA-65")
    purpose = models.CharField(max_length=20, choices=KeyPurpose.choices)

    #: Null for the platform status key and the root key.
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="signing_keys",
        null=True,
        blank=True,
    )

    public_key = models.BinaryField(max_length=4096)

    #: Where the signing service can find the private seed, e.g. a secret
    #: manager path. Never the seed itself.
    private_key_reference = models.CharField(max_length=300, blank=True)

    state = models.CharField(max_length=20, choices=KeyState.choices, default=KeyState.ACTIVE)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "signing_key"
        indexes = [models.Index(fields=["organization", "purpose", "state"])]

    def __str__(self) -> str:
        return f"{self.key_id} ({self.purpose}/{self.state})"

    def is_usable_for_signing(self, now) -> bool:
        """Only ACTIVE keys inside their validity window may sign."""
        if self.state != KeyState.ACTIVE:
            return False
        if self.valid_from > now:
            return False
        return not (self.valid_until and self.valid_until <= now)


class TrustManifest(models.Model):
    """A root-signed, versioned list of the keys clients may trust.

    Version numbers must never go backwards on an installation: an app that has
    seen version N refuses anything older, so a revoked key cannot be restored
    by replaying an old manifest.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(unique=True)
    canonical_bytes = models.BinaryField()
    signature = models.BinaryField(max_length=4096)
    signed_by = models.ForeignKey(SigningKey, on_delete=models.PROTECT, related_name="manifests")
    issued_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trust_manifest"
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Trust manifest v{self.version}"
