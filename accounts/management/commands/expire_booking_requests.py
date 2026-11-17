from django.core.management.base import BaseCommand

from accounts.services import expire_pending_booking_requests


class Command(BaseCommand):
    help = "Expire pending guide booking requests that are at least 24 hours old."

    def handle(self, *args, **options):
        expired_count = expire_pending_booking_requests()
        self.stdout.write(
            self.style.SUCCESS(f"Expired {expired_count} booking request(s).")
        )
