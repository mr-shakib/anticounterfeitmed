"""Run the receipt outbox once, without a Celery worker.

Useful in development and for a one-off catch-up after an incident.
"""

from django.core.management.base import BaseCommand

from apps.verification.tasks import sign_pending_receipts


class Command(BaseCommand):
    help = "Sign pending verification receipts."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        result = sign_pending_receipts(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"signed {result['signed']}, failed {result['failed']}")
        )
