import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import BookingRequest

logger = logging.getLogger(__name__)


def expire_pending_booking_requests(now=None):
    """Expire overdue pending bookings and notify each affected traveler once.

    The service rechecks every candidate under a database lock so a request that
    was answered concurrently is not overwritten. Email delivery happens after
    the database transactions complete.

    Args:
        now: Optional timezone-aware timestamp to use as the current time. The
            current Django time is used when this value is omitted.

    Returns:
        The number of booking requests changed to the expired state.
    """
    now = now or timezone.now()
    expiry_cutoff = now - timedelta(hours=24)
    candidate_ids = list(BookingRequest.objects.filter(
        status=BookingRequest.Status.PENDING,
        created_at__lte=expiry_cutoff,
    ).values_list("pk", flat=True))
    expired_notifications = []

    for booking_id in candidate_ids:
        with transaction.atomic():
            booking = (
                BookingRequest.objects.select_for_update()
                .select_related("traveler", "guide_application")
                .filter(
                    pk=booking_id,
                    status=BookingRequest.Status.PENDING,
                    created_at__lte=expiry_cutoff,
                )
                .first()
            )
            if not booking:
                continue
            booking.status = BookingRequest.Status.EXPIRED
            booking.responded_at = now
            booking.save(update_fields=["status", "responded_at", "updated_at"])
            expired_notifications.append(
                (booking.traveler.email, booking.pk, booking.guide_application.full_name)
            )

    for traveler_email, booking_id, guide_name in expired_notifications:
        sent = send_mail(
            subject="Your guide booking request has expired",
            message=(
                f"Your request to {guide_name} was not answered within 24 hours, "
                "so it has expired. You can choose another available guide or date."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[traveler_email],
            fail_silently=True,
        )
        if not sent:
            logger.warning(
                "Booking expiry notification could not be sent: booking_id=%s",
                booking_id,
            )

    return len(expired_notifications)
