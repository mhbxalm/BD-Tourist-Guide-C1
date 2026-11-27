from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from .forms import (
    GuideAvailabilityRangeForm,
    GuideBookingRequestForm,
    GuideReviewForm,
    GuideSearchForm,
    TravelerRegistrationForm,
)
from .models import BookingRequest, GuideApplication, User
from .services import expire_pending_booking_requests


class TravelerRegistrationFormTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "email": "Traveler@Example.com",
            "first_name": "Amina",
            "last_name": "Rahman",
            "password1": "S3cure!BlueForest92",
            "password2": "S3cure!BlueForest92",
        }
        data.update(overrides)
        return data

    def test_valid_registration_normalizes_email_and_saves_unverified_traveler(self):
        form = TravelerRegistrationForm(data=self.registration_data())

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.email, "traveler@example.com")
        self.assertEqual(user.username, "traveler@example.com")
        self.assertEqual(user.role, User.Role.TRAVELER)
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.check_password("S3cure!BlueForest92"))

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(
            username="traveler@example.com",
            email="traveler@example.com",
            password="S3cure!BlueForest92",
        )
        form = TravelerRegistrationForm(data=self.registration_data())

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_mismatched_password_confirmation_is_rejected(self):
        form = TravelerRegistrationForm(
            data=self.registration_data(password2="Different!BlueForest92")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)


class GuideSearchFormTests(TestCase):
    def test_empty_filters_are_valid_for_unfiltered_search(self):
        # The search view supplies the default sort value for an empty query.
        form = GuideSearchForm(data={"sort": "rating"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sort"], "rating")

    def test_minimum_price_greater_than_maximum_is_rejected(self):
        form = GuideSearchForm(data={"min_price": "5000", "max_price": "4000"})

        self.assertFalse(form.is_valid())
        self.assertIn("max_price", form.errors)

    def test_past_trip_date_is_rejected(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        form = GuideSearchForm(data={"date": yesterday.isoformat()})

        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)


class BookingAndAvailabilityFormTests(TestCase):
    def booking_data(self, **overrides):
        trip_date = timezone.localdate() + timedelta(days=1)
        data = {
            "start_date": trip_date.isoformat(),
            "end_date": trip_date.isoformat(),
            "group_size": "1",
            "meeting_place": "Old Dhaka",
            "notes": "",
            "safety_acknowledged": "on",
        }
        data.update(overrides)
        return data

    def test_one_day_trip_and_minimum_group_size_are_valid(self):
        form = GuideBookingRequestForm(data=self.booking_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["group_size"], 1)
        self.assertEqual(form.cleaned_data["start_date"], form.cleaned_data["end_date"])

    def test_maximum_group_size_is_valid(self):
        form = GuideBookingRequestForm(data=self.booking_data(group_size="100"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["group_size"], 100)

    def test_group_sizes_outside_allowed_bounds_are_rejected(self):
        for group_size in ("0", "101"):
            with self.subTest(group_size=group_size):
                form = GuideBookingRequestForm(
                    data=self.booking_data(group_size=group_size)
                )
                self.assertFalse(form.is_valid())
                self.assertIn("group_size", form.errors)

    def test_end_date_before_start_date_is_rejected(self):
        start = timezone.localdate() + timedelta(days=3)
        end = start - timedelta(days=1)
        form = GuideBookingRequestForm(
            data=self.booking_data(
                start_date=start.isoformat(), end_date=end.isoformat()
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)

    def test_malformed_date_is_rejected_without_exception(self):
        form = GuideBookingRequestForm(data=self.booking_data(start_date="tomorrow"))

        self.assertFalse(form.is_valid())
        self.assertIn("start_date", form.errors)

    def test_exactly_90_inclusive_availability_days_are_allowed(self):
        start = timezone.localdate() + timedelta(days=1)
        end = start + timedelta(days=89)
        form = GuideAvailabilityRangeForm(
            data={"start_date": start.isoformat(), "end_date": end.isoformat()}
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_91_day_availability_range_is_rejected(self):
        start = timezone.localdate() + timedelta(days=1)
        end = start + timedelta(days=90)
        form = GuideAvailabilityRangeForm(
            data={"start_date": start.isoformat(), "end_date": end.isoformat()}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)


class GuideReviewFormTests(TestCase):
    def test_lowest_and_highest_ratings_are_valid(self):
        for rating in ("1", "5"):
            with self.subTest(rating=rating):
                form = GuideReviewForm(
                    data={"rating": rating, "review_text": "Great local guide."}
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_out_of_range_rating_and_short_review_are_rejected(self):
        form = GuideReviewForm(data={"rating": "6", "review_text": "Good"})

        self.assertFalse(form.is_valid())
        self.assertIn("rating", form.errors)
        self.assertIn("review_text", form.errors)


class ExpirePendingBookingRequestsTests(TestCase):
    def setUp(self):
        self.traveler = User.objects.create_user(
            username="traveler@example.test",
            email="traveler@example.test",
            password="S3cure!BlueForest92",
        )
        guide_user = User.objects.create_user(
            username="guide@example.test",
            email="guide@example.test",
            password="S3cure!BlueForest92",
            role=User.Role.GUIDE,
        )
        self.guide = GuideApplication.objects.create(
            user=guide_user,
            full_name="Local Guide",
            bio="A local guide profile.",
            languages="Bangla, English",
            areas_covered="Dhaka",
            daily_rate=Decimal("3000.00"),
            max_group_size=4,
            profile_photo="guide_applications/guide/photo.png",
            id_document="guide_applications/guide/id.pdf",
            status=GuideApplication.Status.VERIFIED,
        )

    def make_booking(self, status=BookingRequest.Status.PENDING, created_at=None):
        trip_date = timezone.localdate() + timedelta(days=10)
        booking = BookingRequest.objects.create(
            traveler=self.traveler,
            guide_application=self.guide,
            start_date=trip_date,
            end_date=trip_date,
            group_size=1,
            meeting_place="Old Dhaka",
            daily_rate_snapshot=Decimal("3000.00"),
            total_price=Decimal("3000.00"),
            status=status,
        )
        if created_at is not None:
            BookingRequest.objects.filter(pk=booking.pk).update(created_at=created_at)
            booking.refresh_from_db()
        return booking

    def test_request_at_24_hour_boundary_expires_and_notifies_once(self):
        now = timezone.now()
        booking = self.make_booking(created_at=now - timedelta(hours=24))

        expired_count = expire_pending_booking_requests(now=now)
        booking.refresh_from_db()

        self.assertEqual(expired_count, 1)
        self.assertEqual(booking.status, BookingRequest.Status.EXPIRED)
        self.assertEqual(booking.responded_at, now)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Local Guide", mail.outbox[0].body)

        self.assertEqual(expire_pending_booking_requests(now=now), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_one_second_before_expiry_remains_pending(self):
        now = timezone.now()
        booking = self.make_booking(
            created_at=now - timedelta(hours=24) + timedelta(seconds=1)
        )

        self.assertEqual(expire_pending_booking_requests(now=now), 0)
        booking.refresh_from_db()

        self.assertEqual(booking.status, BookingRequest.Status.PENDING)
        self.assertEqual(len(mail.outbox), 0)

    def test_non_pending_old_request_is_not_changed(self):
        now = timezone.now()
        booking = self.make_booking(
            status=BookingRequest.Status.CONFIRMED,
            created_at=now - timedelta(days=3),
        )

        self.assertEqual(expire_pending_booking_requests(now=now), 0)
        booking.refresh_from_db()

        self.assertEqual(booking.status, BookingRequest.Status.CONFIRMED)
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_email_delivery_does_not_restore_expired_request(self):
        now = timezone.now()
        booking = self.make_booking(created_at=now - timedelta(hours=25))

        with patch("accounts.services.send_mail", return_value=0):
            with self.assertLogs("accounts.services", level="WARNING"):
                expired_count = expire_pending_booking_requests(now=now)

        booking.refresh_from_db()
        self.assertEqual(expired_count, 1)
        self.assertEqual(booking.status, BookingRequest.Status.EXPIRED)
