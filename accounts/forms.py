import logging
from datetime import timedelta
from pathlib import Path

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone

from .models import GuideApplication, User

logger = logging.getLogger(__name__)


class EmailLoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Email or password is incorrect.",
    }

    def clean(self):
        typed_email = self.cleaned_data.get("username", "").strip()
        account = User.objects.filter(email__iexact=typed_email).first()
        if account and account.is_temporarily_locked:
            until = timezone.localtime(account.locked_until).strftime("%H:%M")
            raise ValidationError(f"This account is temporarily locked. Try again after {until}.")

        if account:
            if account.locked_until and account.locked_until <= timezone.now():
                account.failed_login_attempts = 0
                account.locked_until = None
                account.save(update_fields=["failed_login_attempts", "locked_until"])
            # AuthenticationForm has already cleaned the username field, so
            # update cleaned_data before delegating to its authenticate call.
            self.cleaned_data["username"] = account.username

        try:
            cleaned_data = super().clean()
        except ValidationError:
            if account:
                User.objects.filter(pk=account.pk).update(
                    failed_login_attempts=F("failed_login_attempts") + 1
                )
                account.refresh_from_db(fields=["failed_login_attempts"])
                if account.failed_login_attempts >= 5:
                    account.locked_until = timezone.now() + timedelta(minutes=15)
                    account.save(update_fields=["locked_until"])
                    logger.warning("Account temporarily locked after failed logins: user_id=%s", account.pk)
                    raise ValidationError(
                        "Too many failed attempts. This account is locked for 15 minutes."
                    ) from None
            raise

        if account:
            account.failed_login_attempts = 0
            account.locked_until = None
            account.save(update_fields=["failed_login_attempts", "locked_until"])
        return cleaned_data


class VerifiedPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        return (
            user
            for user in super().get_users(email)
            if user.is_email_verified or user.is_superuser
        )


class PasswordResetSetForm(SetPasswordForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.failed_login_attempts = 0
        user.locked_until = None
        if commit:
            user.save(update_fields=["password", "failed_login_attempts", "locked_until"])
        return user


class GuideApplicationForm(forms.ModelForm):
    """Validate guide profile fields and uploaded application documents."""

    class Meta:
        model = GuideApplication
        fields = [
            "full_name",
            "bio",
            "languages",
            "areas_covered",
            "specialties",
            "daily_rate",
            "max_group_size",
            "profile_photo",
            "id_document",
            "license_document",
        ]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("profile_photo", "id_document", "license_document"):
            uploaded_file = cleaned_data.get(field_name)
            if not uploaded_file:
                continue
            if uploaded_file.size > 5 * 1024 * 1024:
                self.add_error(field_name, "The file must be 5 MB or smaller.")
                continue
            extension = Path(uploaded_file.name).suffix.lower()
            allowed = {".jpg", ".jpeg", ".png"}
            if field_name != "profile_photo":
                allowed.add(".pdf")
            if extension not in allowed:
                self.add_error(field_name, "Upload a JPG, PNG, or PDF file as allowed for this field.")
        return cleaned_data


class GuideSearchForm(forms.Form):
    """Validate filters used to search verified guide profiles."""

    SORT_CHOICES = [
        ("rating", "Top rated"),
        ("price", "Lowest price"),
        ("tours", "Most completed tours"),
    ]

    destination = forms.CharField(required=False, max_length=100)
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    language = forms.CharField(required=False, max_length=60)
    specialty = forms.CharField(required=False, max_length=80)
    min_price = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2)
    max_price = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2)
    min_rating = forms.DecimalField(
        required=False,
        min_value=1,
        max_value=5,
        max_digits=2,
        decimal_places=1,
    )
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES, initial="rating")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
            if field_name == "sort":
                field.widget.attrs["class"] = "form-select"
        self.fields["destination"].widget.attrs["placeholder"] = "e.g. Sylhet"
        self.fields["language"].widget.attrs["placeholder"] = "Bangla, English"
        self.fields["specialty"].widget.attrs["placeholder"] = "Nature, food…"
        self.fields["min_price"].widget.attrs.update({"step": "100", "placeholder": "Any"})
        self.fields["max_price"].widget.attrs.update({"step": "100", "placeholder": "Any"})
        self.fields["min_rating"].widget.attrs.update({"step": "0.5", "min": "1", "max": "5"})
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean(self):
        cleaned_data = super().clean()
        minimum = cleaned_data.get("min_price")
        maximum = cleaned_data.get("max_price")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("max_price", "Maximum price must be at least the minimum price.")

        trip_date = cleaned_data.get("date")
        if trip_date and trip_date < timezone.localdate():
            self.add_error("date", "Choose today or a future date.")
        return cleaned_data


class GuideBookingRequestForm(forms.Form):
    """Validate a traveler's requested dates, group size, and meeting details."""

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    group_size = forms.IntegerField(
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    )
    meeting_place = forms.CharField(
        max_length=240,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Where should you meet?"}
        ),
    )
    notes = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "placeholder": "Anything the guide should know?"}
        ),
    )
    safety_acknowledged = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        minimum_date = timezone.localdate().isoformat()
        self.fields["start_date"].widget.attrs["min"] = minimum_date
        self.fields["end_date"].widget.attrs["min"] = minimum_date

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        today = timezone.localdate()
        if start_date and start_date < today:
            self.add_error("start_date", "Choose today or a future date.")
        if end_date and end_date < today:
            self.add_error("end_date", "Choose today or a future date.")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned_data


class GuideReviewForm(forms.Form):
    """Validate a review submitted after a guide marks a tour complete."""

    rating = forms.TypedChoiceField(
        choices=[(value, f"{value} star{'s' if value != 1 else ''}") for value in range(1, 6)],
        coerce=int,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    review_text = forms.CharField(
        min_length=5,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Share details that may help other travelers.",
            }
        ),
    )

    def clean_review_text(self):
        review_text = self.cleaned_data["review_text"].strip()
        if len(review_text) < 5:
            raise forms.ValidationError("Write at least 5 characters for your review.")
        return review_text


class GuideReplyForm(forms.Form):
    guide_reply = forms.CharField(
        min_length=2,
        max_length=1200,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Write a public reply to this review.",
            }
        ),
    )

    def clean_guide_reply(self):
        guide_reply = self.cleaned_data["guide_reply"].strip()
        if len(guide_reply) < 2:
            raise forms.ValidationError("Write at least 2 characters for your reply.")
        return guide_reply


class GuideAvailabilityRangeForm(forms.Form):
    """Validate an inclusive range of dates a guide is available."""

    start_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}
        )
    )
    end_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        minimum_date = timezone.localdate().isoformat()
        self.fields["start_date"].widget.attrs["min"] = minimum_date
        self.fields["end_date"].widget.attrs["min"] = minimum_date

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        today = timezone.localdate()

        if start_date and start_date < today:
            self.add_error("start_date", "Choose today or a future date.")
        if end_date and end_date < today:
            self.add_error("end_date", "Choose today or a future date.")
        if start_date and end_date:
            if end_date < start_date:
                self.add_error(
                    "end_date", "End date must be on or after the start date."
                )
            elif (end_date - start_date).days >= 90:
                self.add_error("end_date", "Choose a date range of 90 days or fewer.")

        return cleaned_data


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name"]
        labels = {"first_name": "First name", "last_name": "Last name"}
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_first_name(self):
        value = self.cleaned_data["first_name"].strip()
        if not value:
            raise forms.ValidationError("Enter your first name.")
        return value

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()


class TravelerRegistrationForm(UserCreationForm):
    email = forms.EmailField(label="Email address")
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data["first_name"].strip()
        if not first_name:
            raise forms.ValidationError("Enter your first name.")
        return first_name

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.role = User.Role.TRAVELER
        user.is_email_verified = False
        if commit:
            user.save()
        return user
