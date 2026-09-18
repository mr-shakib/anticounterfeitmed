"""Create or update a staff account for local development.

The portal needs three things that are easy to get individually wrong: a user
with a usable password, an enabled membership of an organization, and — for
privileged roles — an enrolled second factor. Missing any one produces a
different and not very informative refusal, so this sets up all three at once
and prints a working sign-in code.

Development only. Real accounts are created through organization approval and
staff invitation, and their second factor is enrolled by the person who owns it.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.organizations import mfa
from apps.organizations.models import (
    ApprovalStatus,
    Organization,
    OrganizationType,
    StaffMembership,
    StaffRole,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update a staff account for local development."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", default="devpassword123")
        parser.add_argument(
            "--role",
            default=StaffRole.RELEASE_MANAGER,
            choices=[choice[0] for choice in StaffRole.choices],
        )
        parser.add_argument(
            "--organization",
            default=None,
            help="Organization name. Defaults to a sensible one for the role.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("create_staff is only available with DEBUG on")

        role = options["role"]
        is_admin = role == StaffRole.PLATFORM_ADMIN
        org_name = options["organization"] or (
            "Platform Operator" if is_admin else "Demo Pharmaceuticals Ltd"
        )

        organization, _ = Organization.objects.get_or_create(
            name=org_name,
            defaults={
                "type": OrganizationType.PLATFORM if is_admin else OrganizationType.MANUFACTURER,
                "approval_status": ApprovalStatus.APPROVED,
                "approved_at": timezone.now(),
            },
        )

        user, created = User.objects.get_or_create(username=options["username"])
        user.set_password(options["password"])
        user.save()

        membership, _ = StaffMembership.objects.get_or_create(
            user=user,
            organization=organization,
            defaults={"role": role},
        )
        membership.role = role
        membership.is_enabled = True

        # Privileged roles cannot sign in without a second factor, so enrol one
        # rather than leaving the account in a state that refuses every action.
        if membership.is_privileged:
            membership.totp_secret = membership.totp_secret or mfa.new_secret()
            membership.mfa_enabled = True
            membership.mfa_confirmed_at = timezone.now()
        membership.save()

        self.stdout.write(self.style.SUCCESS(
            f"{'created' if created else 'updated'} {user.get_username()}"
        ))
        self.stdout.write(f"  organization : {organization.name}")
        self.stdout.write(f"  role         : {role}")
        self.stdout.write(f"  password     : {options['password']}")
        if membership.is_privileged:
            self.stdout.write(
                f"  second factor: enrolled — current code "
                f"{mfa.now_code(membership.totp_secret)}"
            )
            self.stdout.write(
                "  (codes rotate every 30s; run "
                "`make staff-code USER=%s` for a fresh one)" % user.get_username()
            )
