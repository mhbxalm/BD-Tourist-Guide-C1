import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class UserManager(DjangoUserManager):
    """Create project users with the appropriate application role."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Authenticated traveler, guide, or administrator account."""

    objects = UserManager()
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    class Role(models.TextChoices):
        TRAVELER = "traveler", "Traveler"
        GUIDE = "guide", "Guide"
        ADMIN = "admin", "Administrator"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TRAVELER)
    is_email_verified = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

    @property
    def is_temporarily_locked(self):
        """Return whether a failed-login lock is still active."""
        return self.locked_until is not None and self.locked_until > timezone.now()

    def __str__(self):
        return self.email


def guide_upload_path(instance, filename):
    """Build a private, non-guessable path for a guide application upload.

    Args:
        instance: Guide application that owns the uploaded file.
        filename: Original client-provided filename; only its extension is kept.

    Returns:
        A relative path under ``guide_applications/`` with a random filename.
    """
    from pathlib import Path

    suffix = Path(filename).suffix.lower()
    return f"guide_applications/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class GuideApplication(models.Model):
    """Guide profile and its administrator-review lifecycle."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="guide_applications"
    )
    full_name = models.CharField(max_length=160)
    bio = models.TextField(max_length=2000)
    languages = models.CharField(max_length=300, help_text="Separate languages with commas")
    areas_covered = models.CharField(
        max_length=500, help_text="Separate destinations with commas"
    )
    specialties = models.CharField(
        max_length=500, blank=True, help_text="For example, history, food, nature"
    )
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(1)],
    )
    average_rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    review_count = models.PositiveIntegerField(default=0)
    completed_tours = models.PositiveIntegerField(default=0)
    is_demo = models.BooleanField(default=False, db_index=True)
    max_group_size = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    profile_photo = models.FileField(
        upload_to=guide_upload_path,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png"])],
    )
    id_document = models.FileField(
        upload_to=guide_upload_path,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "pdf"])],
    )
    license_document = models.FileField(
        upload_to=guide_upload_path,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "pdf"])],
        blank=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="reviewed_guide_applications",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.get_status_display()})"


class GuideAvailability(models.Model):
    """A calendar date on which a guide is open to booking requests."""

    guide_application = models.ForeignKey(
        GuideApplication,
        on_delete=models.CASCADE,
        related_name="availability_dates",
    )
    available_date = models.DateField()

    class Meta:
        ordering = ["available_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["guide_application", "available_date"],
                name="unique_guide_available_date",
            )
        ]

    def __str__(self):
        return f"{self.guide_application.full_name}: {self.available_date}"


class BookingRequest(models.Model):
    """Traveler request for a date range with a verified guide."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        COMPLETED = "completed", "Completed"

    traveler = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="booking_requests"
    )
    guide_application = models.ForeignKey(
        GuideApplication,
        on_delete=models.PROTECT,
        related_name="booking_requests",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    group_size = models.PositiveSmallIntegerField()
    meeting_place = models.CharField(max_length=240)
    notes = models.TextField(max_length=1000, blank=True)
    daily_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    responded_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def number_of_days(self):
        """Return the inclusive number of calendar days in the requested trip."""
        return (self.end_date - self.start_date).days + 1

    @property
    def expires_at(self):
        """Return the time when this unanswered request reaches its 24-hour limit."""
        return self.created_at + timedelta(hours=24)

    def __str__(self):
        return f"Booking #{self.pk} - {self.get_status_display()}"


class GuideReview(models.Model):
    """Traveler feedback for one completed booking and optional guide reply."""

    booking = models.OneToOneField(
        BookingRequest,
        on_delete=models.CASCADE,
        related_name="review",
    )
    guide_application = models.ForeignKey(
        GuideApplication,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review_text = models.TextField(max_length=2000)
    guide_reply = models.TextField(max_length=1200, blank=True)
    guide_replied_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating} star review for {self.guide_application.full_name}"


class GuideDecisionLog(models.Model):
    """Audit record for an administrator's guide-application decision."""

    application = models.ForeignKey(
        GuideApplication, on_delete=models.CASCADE, related_name="decision_logs"
    )
    administrator = models.ForeignKey(User, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, choices=GuideApplication.Status.choices)
    reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-decided_at"]

    def __str__(self):
        return f"{self.get_decision_display()} by {self.administrator}"
