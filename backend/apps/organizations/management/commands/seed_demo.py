"""Seed a development environment with one activated package.

Prints the raw token once, for local testing. This command is for development
only: it provisions keys into the local keystore and signs in-process, both of
which are refused outside DEBUG.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from apps.activation.services import activate_units
from apps.catalog.models import Batch, Product
from apps.organizations.models import (
    ApprovalStatus,
    Organization,
    OrganizationType,
    StaffMembership,
    StaffRole,
)
from apps.qc.models import ManufacturingStep
from apps.qc.services import record_completion
from apps.serialization.models import PackageUnit
from apps.serialization.services import create_print_job
from apps.trust.models import KeyPurpose
from apps.trust.services import provision_signing_key, publish_trust_manifest

User = get_user_model()


class Command(BaseCommand):
    help = "Create a demo manufacturer, batch and activated units."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=3)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is only available with DEBUG on")

        count = options["count"]

        org, _ = Organization.objects.get_or_create(
            name="Demo Pharmaceuticals Ltd",
            defaults={
                "type": OrganizationType.MANUFACTURER,
                "approval_status": ApprovalStatus.APPROVED,
                "approved_at": timezone.now(),
            },
        )
        user, created = User.objects.get_or_create(username="demo-release-manager")
        if created:
            user.set_unusable_password()
            user.save()
        membership, _ = StaffMembership.objects.get_or_create(
            user=user,
            organization=org,
            defaults={"role": StaffRole.RELEASE_MANAGER, "mfa_enabled": True},
        )

        if not org.signing_keys.filter(purpose=KeyPurpose.ACTIVATION).exists():
            provision_signing_key(purpose=KeyPurpose.ACTIVATION, organization=org)
        from apps.trust.models import SigningKey

        for purpose in (KeyPurpose.ROOT, KeyPurpose.STATUS):
            if not SigningKey.objects.filter(purpose=purpose).exists():
                provision_signing_key(purpose=purpose)

        product, _ = Product.objects.get_or_create(
            manufacturer=org,
            brand="Napa",
            defaults={
                "generic": "Paracetamol",
                "strength": "500 mg",
                "dosage_form": "Tablet",
                "pack_description": "Strip of 10 tablets",
            },
        )
        batch = Batch.objects.create(
            product=product,
            batch_number=f"BN-DEMO-{timezone.now().strftime('%H%M%S')}",
            manufactured_on=date.today() - timedelta(days=10),
            expires_on=date.today() + timedelta(days=540),
            planned_unit_count=count,
        )

        result = create_print_job(batch=batch, count=count, created_by="seed_demo")
        now = timezone.now()
        for issued in result.units:
            unit = PackageUnit.objects.get(pk=issued.unit_id)
            for step in (
                ManufacturingStep.PRINTED,
                ManufacturingStep.QC_PASSED,
                ManufacturingStep.COATED,
            ):
                record_completion(
                    unit=unit,
                    step=step,
                    completed_at=now,
                    recorded_by=user,
                    source_reference="seed_demo",
                )

        units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
        outcome = activate_units(batch=batch, units=units, membership=membership)
        manifest = publish_trust_manifest()

        self.stdout.write(self.style.SUCCESS(f"activated {len(outcome.succeeded)} units"))
        self.stdout.write(f"trust manifest version {manifest.version}")
        self.stdout.write("")
        self.stdout.write("Tokens (development only, printed once):")
        for issued in result.units:
            self.stdout.write(f"  {issued.external_reference}  {issued.token}")
