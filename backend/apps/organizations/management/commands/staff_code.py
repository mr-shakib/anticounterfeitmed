"""Print a current second-factor code for a local staff account.

Development only, for signing in without an authenticator app on a phone.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.organizations import mfa
from apps.organizations.models import StaffMembership


class Command(BaseCommand):
    help = "Print a current TOTP code for a local staff account."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("staff_code is only available with DEBUG on")

        membership = StaffMembership.objects.filter(
            user__username=options["username"]
        ).first()
        if membership is None:
            raise CommandError(f"no membership for {options['username']}")
        if not membership.totp_secret:
            raise CommandError(
                f"{options['username']} has no second factor enrolled"
            )
        self.stdout.write(mfa.now_code(membership.totp_secret))
