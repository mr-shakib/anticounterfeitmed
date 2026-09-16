"""Consumer sessions, challenges, operations, events and receipts.

The correctness guarantee of the whole system lives in this module's
constraints: a partial unique index permits at most one FIRST_REDEMPTION per
unit, so concurrency safety is enforced by PostgreSQL rather than by
application logic that could race with itself.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.serialization.models import PackageUnit


class ConsumerSession(models.Model):
    """An anonymous per-installation session.

    Created only after app attestation succeeds. Reinstalling produces a new
    session; that is a new installation identity, not evidence about who is
    holding the phone.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: SHA-256 of the opaque session credential. The credential itself is
    #: returned to the app once and never stored.
    credential_sha256 = models.BinaryField(max_length=32)

    installation_id = models.CharField(max_length=64, blank=True)
    app_id = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "consumer_session"
        constraints = [
            models.UniqueConstraint(
                fields=["credential_sha256"], name="uniq_session_credential"
            )
        ]

    def __str__(self) -> str:
        return f"Session {self.id}"

    def is_usable(self, now) -> bool:
        return self.revoked_at is None and self.expires_at > now


class VerificationChallenge(models.Model):
    """A short-lived, single-use permission to attempt one confirmation.

    Bound to session, unit, intended action and the credential version that was
    previewed, so a challenge issued against one credential cannot be spent
    against a different one.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ConsumerSession, on_delete=models.PROTECT, related_name="challenges"
    )
    unit = models.ForeignKey(PackageUnit, on_delete=models.PROTECT, related_name="challenges")

    credential_version = models.PositiveIntegerField()
    intended_action = models.CharField(max_length=20, default="CONFIRM")

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "verification_challenge"
        indexes = [models.Index(fields=["session", "unit"])]

    def is_spendable(self, now) -> bool:
        return self.consumed_at is None and self.expires_at > now


class VerificationOutcome(models.TextChoices):
    VERIFIED_FIRST = "VERIFIED_FIRST", "First verification recorded"
    PREVIOUSLY_VERIFIED = "PREVIOUSLY_VERIFIED", "Previously verified"
    NOT_ACTIVATED = "NOT_ACTIVATED", "Not activated"
    NOT_FOUND = "NOT_FOUND", "Code not found"
    EXPIRED = "EXPIRED", "Expired"
    RECALLED = "RECALLED", "Recalled"
    RESTRICTED = "RESTRICTED", "Restricted"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL", "Invalid credential"


class VerificationOperation(models.Model):
    """One idempotent confirmation attempt.

    The unique constraint on (session, idempotency_key) is what makes a retry
    return the original outcome instead of creating a second event.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ConsumerSession, on_delete=models.PROTECT, related_name="operations"
    )
    idempotency_key = models.CharField(max_length=80)

    #: Digest of the request body, so the same key with different content is a
    #: conflict rather than a silent replay of an unrelated result.
    request_digest = models.CharField(max_length=64)

    unit = models.ForeignKey(
        PackageUnit, on_delete=models.PROTECT, related_name="operations", null=True, blank=True
    )
    outcome = models.CharField(max_length=30, choices=VerificationOutcome.choices, blank=True)
    event = models.ForeignKey(
        "verification.VerificationEvent",
        on_delete=models.PROTECT,
        related_name="operations",
        null=True,
        blank=True,
    )
    receipt_ready = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "verification_operation"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "idempotency_key"], name="uniq_operation_idempotency"
            )
        ]

    def __str__(self) -> str:
        return f"Operation {self.id} ({self.outcome or 'pending'})"


class VerificationEventType(models.TextChoices):
    FIRST_REDEMPTION = "FIRST_REDEMPTION", "First redemption"
    REPEAT_CHECK = "REPEAT_CHECK", "Repeat check"
    DECLINED = "DECLINED", "Declined attempt"
    PREACTIVATION_ATTEMPT = "PREACTIVATION_ATTEMPT", "Pre-activation attempt"


class VerificationEvent(models.Model):
    """A committed, server-side verification event.

    This records that the server committed an outcome. It is not evidence that
    the consumer read the screen that came back.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.ForeignKey(PackageUnit, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=30, choices=VerificationEventType.choices)
    session = models.ForeignKey(
        ConsumerSession, on_delete=models.PROTECT, related_name="events", null=True, blank=True
    )
    previous_event = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="subsequent", null=True, blank=True
    )
    server_time = models.DateTimeField()
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "verification_event"
        constraints = [
            # The guarantee. At most one first redemption per unit, enforced by
            # the database so 100 concurrent attempts cannot produce two.
            models.UniqueConstraint(
                fields=["unit"],
                condition=models.Q(event_type=VerificationEventType.FIRST_REDEMPTION),
                name="one_first_redemption_per_unit",
            )
        ]
        indexes = [
            models.Index(fields=["unit", "server_time"]),
            models.Index(fields=["session"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.unit_id}"


class ReceiptStatus(models.TextChoices):
    PENDING = "PENDING", "Pending signature"
    SIGNED = "SIGNED", "Signed"
    FAILED = "FAILED", "Failed, will retry"


class SignedReceipt(models.Model):
    """Outbox row created in the same transaction as its event.

    If signing or delivery fails after the event has committed, the redemption
    is never undone: the app shows a pending state and a worker signs the
    already-committed event.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(
        VerificationEvent, on_delete=models.PROTECT, related_name="receipt"
    )
    status = models.CharField(
        max_length=20, choices=ReceiptStatus.choices, default=ReceiptStatus.PENDING
    )
    canonical_bytes = models.BinaryField(null=True, blank=True)
    signature = models.BinaryField(max_length=4096, null=True, blank=True)
    signing_key_id = models.CharField(max_length=80, blank=True)

    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "signed_receipt"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"Receipt for {self.event_id} ({self.status})"
