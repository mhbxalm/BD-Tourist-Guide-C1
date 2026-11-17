import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.db.models import Avg, Count, F
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .forms import (
    GuideApplicationForm,
    GuideAvailabilityDateForm,
    GuideBookingRequestForm,
    GuideReplyForm,
    GuideReviewForm,
    GuideSearchForm,
    TravelerRegistrationForm,
    UserProfileForm,
)
from .models import (
    BookingRequest,
    GuideApplication,
    GuideAvailability,
    GuideDecisionLog,
    GuideReview,
    User,
)
from .services import expire_pending_booking_requests
from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def register(request):
    """Create a traveler account and send its email-verification link.

    A valid POST creates an unverified account. Invalid input redisplays the
    registration form with field-level errors.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = TravelerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        verification_url = request.build_absolute_uri(
            reverse("accounts:verify_email", kwargs={"uidb64": uid, "token": token})
        )
        send_mail(
            subject="Verify your BD Tourist Guide account",
            message=f"Open this link to verify your email address: {verification_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return render(request, "accounts/registration_sent.html", {"email": user.email})
    return render(request, "accounts/register.html", {"form": form})


def verify_email(request, uidb64, token):
    """Validate a signed verification link and activate the user's email.

    Args:
        uidb64: URL-safe encoded primary key of the account to verify.
        token: Time-sensitive token generated for that account.

    Returns:
        A redirect to login on success, or an invalid-link page with HTTP 400.
    """
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = get_object_or_404(User, pk=user_id)
    except (TypeError, ValueError, OverflowError):
        user = None
    if user and email_verification_token.check_token(user, token):
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        messages.success(request, "Your email is verified. You can now log in and book guides.")
        return redirect("accounts:login")
    return render(request, "accounts/verification_invalid.html", status=400)


@login_required
def dashboard(request):
    """Render the signed-in user's dashboard and shared guide search results."""
    expire_pending_booking_requests()
    context = guide_search_context(request)
    context["my_bookings"] = BookingRequest.objects.filter(
        traveler=request.user
    ).select_related("guide_application")[:5]
    guide_application = GuideApplication.objects.filter(
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    ).first()
    context["guide_pending_bookings"] = (
        BookingRequest.objects.filter(
            guide_application=guide_application,
            status=BookingRequest.Status.PENDING,
        ).select_related("traveler")[:5]
        if guide_application
        else []
    )
    context["has_verified_guide_profile"] = bool(guide_application)
    context["guide_unanswered_reviews"] = (
        GuideReview.objects.filter(
            guide_application=guide_application,
            guide_reply="",
        ).count()
        if guide_application
        else 0
    )
    return render(request, "accounts/dashboard.html", context)


@login_required
def edit_profile(request):
    """Update the authenticated user's first and last name."""
    form = UserProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your name has been updated.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/profile_form.html", {"form": form})


@login_required
def manage_guide_availability(request):
    guide = get_object_or_404(
        GuideApplication,
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    )
    form = GuideAvailabilityDateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        available_date = form.cleaned_data["available_date"]
        with transaction.atomic():
            GuideApplication.objects.select_for_update().get(pk=guide.pk)
            has_booking = BookingRequest.objects.filter(
                guide_application=guide,
                status__in=[BookingRequest.Status.PENDING, BookingRequest.Status.CONFIRMED],
                start_date__lte=available_date,
                end_date__gte=available_date,
            ).exists()
            if has_booking:
                form.add_error(
                    "available_date",
                    "You have a pending or confirmed booking on this date.",
                )
            else:
                _, created = GuideAvailability.objects.get_or_create(
                    guide_application=guide,
                    available_date=available_date,
                )
        if not form.errors:
            if created:
                messages.success(request, "Availability date added.")
            else:
                messages.info(request, "That date is already on your availability calendar.")
            return redirect("accounts:manage_guide_availability")

    today = timezone.localdate()
    availability_dates = guide.availability_dates.filter(
        available_date__gte=today
    )[:90]
    return render(
        request,
        "accounts/guide_availability.html",
        {
            "guide": guide,
            "form": form,
            "availability_dates": availability_dates,
        },
    )


@login_required
@require_POST
def remove_guide_availability(request, availability_id):
    guide = get_object_or_404(
        GuideApplication,
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    )
    with transaction.atomic():
        availability = get_object_or_404(
            GuideAvailability.objects.select_for_update(),
            pk=availability_id,
            guide_application=guide,
        )
        has_booking = BookingRequest.objects.filter(
            guide_application=guide,
            status__in=[BookingRequest.Status.PENDING, BookingRequest.Status.CONFIRMED],
            start_date__lte=availability.available_date,
            end_date__gte=availability.available_date,
        ).exists()
        if has_booking:
            messages.error(
                request,
                "This date is attached to a pending or confirmed booking and cannot be removed.",
            )
        else:
            availability.delete()
            messages.success(request, "Availability date removed.")
    return redirect("accounts:manage_guide_availability")


def guide_search_context(request):
    """Build the verified-guide queryset and search-form template context.

    Filters include destination, trip date, language, specialty, daily-price
    range, and minimum rating. Results are limited to the first 24 guides.

    Returns:
        A dictionary containing ``guides``, ``search_form``, ``has_search``,
        and the selected ``trip_date`` value.
    """
    guides = GuideApplication.objects.filter(status=GuideApplication.Status.VERIFIED)
    form = GuideSearchForm(request.GET if request.GET else {"sort": "rating"})
    has_search = False
    trip_date = ""
    if form.is_valid():
        filters = form.cleaned_data
        destination = filters.get("destination", "").strip()
        language = filters.get("language", "").strip()
        specialty = filters.get("specialty", "").strip()
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")
        min_rating = filters.get("min_rating")
        trip_date = filters.get("date")
        trip_date_value = trip_date.isoformat() if trip_date else ""
        has_search = any(
            [destination, language, specialty, min_price, max_price, min_rating, trip_date]
        )

        if destination:
            guides = guides.filter(areas_covered__icontains=destination)
        if language:
            guides = guides.filter(languages__icontains=language)
        if specialty:
            guides = guides.filter(specialties__icontains=specialty)
        if min_price is not None:
            guides = guides.filter(daily_rate__gte=min_price)
        if max_price is not None:
            guides = guides.filter(daily_rate__lte=max_price)
        if min_rating is not None:
            guides = guides.filter(average_rating__gte=min_rating)
        if trip_date:
            guides = guides.filter(
                availability_dates__available_date=trip_date
            ).distinct()

        sort_fields = {
            "price": ("daily_rate", "full_name"),
            "tours": ("-completed_tours", "-average_rating", "full_name"),
            "rating": ("-average_rating", "-review_count", "daily_rate"),
        }
        guides = guides.order_by(*sort_fields.get(filters.get("sort"), sort_fields["rating"]))
    else:
        guides = guides.none()
        has_search = bool(request.GET)

    guides = guides.select_related("user")[:24]
    return {
        "guides": guides,
        "search_form": form,
        "has_search": has_search,
        "trip_date": trip_date_value if form.is_valid() else trip_date,
    }


def home(request):
    """Render the public homepage with destinations and verified guides."""
    return render(
        request,
        "home.html",
        {
            **guide_search_context(request),
            "popular_destinations": [
                {
                    "name": "Cox’s Bazar",
                    "description": "Sea, sand, and sunset walks",
                    "image": "image/destinations/cox_bazar.jpeg",
                },
                {
                    "name": "Sylhet",
                    "description": "Tea gardens and green hills",
                    "image": "image/destinations/sylhet.jpg",
                },
                {
                    "name": "Bandarban",
                    "description": "Mountain ridges and quiet trails",
                    "image": "image/destinations/bandarban.jpg",
                },
                {
                    "name": "Sundarbans",
                    "description": "Mangrove waterways and wildlife",
                    "image": "image/destinations/sundarbans.jpeg",
                },
                {
                    "name": "Old Dhaka",
                    "description": "Heritage, architecture, and street food",
                    "image": "image/destinations/old_dhaka.jpeg",
                },
            ],
        },
    )


@login_required
def apply_as_guide(request):
    """Submit a guide application for administrator review.

    The form validates the profile and uploaded documents. A successful
    submission creates a pending application and updates the user's profile
    name and role where appropriate.
    """
    previous = GuideApplication.objects.filter(user=request.user).order_by("-created_at").first()
    if previous and previous.status in {
        GuideApplication.Status.PENDING,
        GuideApplication.Status.VERIFIED,
    }:
        messages.info(request, f"Your guide application is {previous.get_status_display().lower()}.")
        return redirect("accounts:dashboard")

    form = GuideApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        application.user = request.user
        application.status = GuideApplication.Status.PENDING
        application.save()
        name_parts = application.full_name.strip().split()
        request.user.first_name = name_parts[0]
        request.user.last_name = " ".join(name_parts[1:])
        if request.user.role != User.Role.ADMIN:
            request.user.role = User.Role.GUIDE
        request.user.save(update_fields=["first_name", "last_name", "role"])
        messages.success(request, "Your guide application was submitted for review.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/guide_application_form.html", {"form": form})


def is_administrator(user):
    return user.is_authenticated and (user.is_staff or user.role == User.Role.ADMIN)


@login_required
def guide_application_list(request):
    if not is_administrator(request.user):
        raise Http404
    applications = GuideApplication.objects.filter(
        status=GuideApplication.Status.PENDING
    ).select_related("user")
    return render(
        request,
        "accounts/guide_application_list.html",
        {"applications": applications},
    )


@login_required
def guide_application_review(request, application_id):
    """Approve or reject a pending guide application as an administrator.

    Rejections require a reason. Each completed decision is recorded in the
    guide decision audit log and is communicated to the applicant by email.
    """
    if not is_administrator(request.user):
        raise Http404
    application = get_object_or_404(
        GuideApplication.objects.select_related("user"), pk=application_id
    )
    if request.method == "POST":
        decision = request.POST.get("decision")
        reason = request.POST.get("reason", "").strip()
        if application.status != GuideApplication.Status.PENDING:
            messages.error(request, "This application has already been reviewed.")
        elif decision == GuideApplication.Status.REJECTED and not reason:
            messages.error(request, "Enter a reason before rejecting this application.")
        elif decision not in {
            GuideApplication.Status.VERIFIED,
            GuideApplication.Status.REJECTED,
        }:
            messages.error(request, "Choose approve or reject.")
        else:
            with transaction.atomic():
                application = GuideApplication.objects.select_for_update().get(
                    pk=application.pk
                )
                if application.status != GuideApplication.Status.PENDING:
                    messages.error(request, "This application has already been reviewed.")
                    return redirect("accounts:guide_application_list")
                application.status = decision
                application.reviewed_by = request.user
                application.reviewed_at = timezone.now()
                application.rejection_reason = (
                    reason if decision == GuideApplication.Status.REJECTED else ""
                )
                application.save(
                    update_fields=[
                        "status",
                        "reviewed_by",
                        "reviewed_at",
                        "rejection_reason",
                        "updated_at",
                    ]
                )
                GuideDecisionLog.objects.create(
                    application=application,
                    administrator=request.user,
                    decision=decision,
                    reason=application.rejection_reason,
                )
            if decision == GuideApplication.Status.VERIFIED:
                send_mail(
                    "Your guide application is approved",
                    "Your guide profile has been verified and approved on BD Tourist Guide.",
                    settings.DEFAULT_FROM_EMAIL,
                    [application.user.email],
                    fail_silently=True,
                )
                messages.success(request, "Guide approved and marked as verified.")
            else:
                send_mail(
                    "Update on your guide application",
                    f"Your application was not approved. Reason: {reason}",
                    settings.DEFAULT_FROM_EMAIL,
                    [application.user.email],
                    fail_silently=True,
                )
                messages.success(request, "Application rejected and the reason was sent.")
            return redirect("accounts:guide_application_list")
    return render(
        request,
        "accounts/guide_application_review.html",
        {"application": application},
    )


@login_required
def guide_application_document(request, application_id, document_type):
    if not is_administrator(request.user):
        raise Http404
    allowed_documents = {
        "id_document": "Identity document",
        "license_document": "License document",
        "profile_photo": "Profile photo",
    }
    if document_type not in allowed_documents:
        raise Http404
    application = get_object_or_404(GuideApplication, pk=application_id)
    document = getattr(application, document_type)
    if not document:
        raise Http404
    return FileResponse(
        document.open("rb"),
        as_attachment=True,
        filename=f"{allowed_documents[document_type]}{document.name[document.name.rfind('.'):]}" ,
    )


@login_required
def book_guide(request, guide_id):
    """Create a booking request with a verified guide.

    The traveler must have a verified email. The view checks guide status,
    group size, date availability, and overlapping requests before it creates
    a pending booking and notifies the guide.
    """
    guide = get_object_or_404(
        GuideApplication.objects.select_related("user"),
        pk=guide_id,
        status=GuideApplication.Status.VERIFIED,
    )
    if request.user.role != User.Role.TRAVELER:
        messages.error(request, "Only traveler accounts can send booking requests.")
        return redirect("accounts:dashboard")

    has_prior_booking = BookingRequest.objects.filter(traveler=request.user).exists()
    if not request.user.is_email_verified:
        return render(
            request,
            "accounts/booking_form.html",
            {
                "guide": guide,
                "email_unverified": True,
                "has_prior_booking": has_prior_booking,
            },
            status=403,
        )

    initial = {
        key: request.GET[key]
        for key in ("start_date", "end_date")
        if request.GET.get(key)
    }
    form = GuideBookingRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["group_size"] > guide.max_group_size:
            form.add_error(
                "group_size",
                f"This guide can take up to {guide.max_group_size} travelers.",
            )
        if not has_prior_booking and not form.cleaned_data.get("safety_acknowledged"):
            form.add_error(
                "safety_acknowledged",
                "Please review and acknowledge the traveler safety guidance.",
            )

        if not form.errors:
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            day_count = (end_date - start_date).days + 1
            booking = None
            with transaction.atomic():
                application = GuideApplication.objects.select_for_update().filter(
                    pk=guide.pk, status=GuideApplication.Status.VERIFIED
                ).first()
                if not application:
                    form.add_error(
                        None,
                        "This guide is no longer available for booking.",
                    )
                else:
                    available_days = list(
                        GuideAvailability.objects.select_for_update()
                        .filter(
                            guide_application=application,
                            available_date__gte=start_date,
                            available_date__lte=end_date,
                        )
                        .values_list("available_date", flat=True)
                    )
                    if len(available_days) != day_count:
                        form.add_error(
                            None,
                            "The guide is not available for every day in those dates. Choose another date range.",
                        )
                    else:
                        overlapping = BookingRequest.objects.filter(
                            guide_application=application,
                            status__in=[
                                BookingRequest.Status.PENDING,
                                BookingRequest.Status.CONFIRMED,
                            ],
                            start_date__lte=end_date,
                            end_date__gte=start_date,
                        ).exists()
                        if overlapping:
                            form.add_error(
                                None,
                                "The guide already has a pending or confirmed request during those dates.",
                            )
                        else:
                            total_price = application.daily_rate * day_count
                            booking = BookingRequest.objects.create(
                                traveler=request.user,
                                guide_application=application,
                                start_date=start_date,
                                end_date=end_date,
                                group_size=form.cleaned_data["group_size"],
                                meeting_place=form.cleaned_data["meeting_place"],
                                notes=form.cleaned_data["notes"],
                                daily_rate_snapshot=application.daily_rate,
                                total_price=total_price,
                                status=BookingRequest.Status.PENDING,
                            )

            if booking:
                sent = send_mail(
                    subject="New booking request on BD Tourist Guide",
                    message=(
                        f"Hello {guide.full_name},\n\n"
                        f"{request.user.email} requested a tour from {booking.start_date} "
                        f"to {booking.end_date} for {booking.group_size} traveler(s). "
                        f"Meeting place: {booking.meeting_place}. "
                        f"Total: BDT {booking.total_price}.\n"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[guide.user.email],
                    fail_silently=True,
                )
                if not sent:
                    logger.warning("Booking notification email could not be sent: booking_id=%s", booking.pk)
                messages.success(request, "Your booking request was sent to the guide.")
                return redirect("accounts:booking_detail", booking_id=booking.pk)

    return render(
        request,
        "accounts/booking_form.html",
        {
            "guide": guide,
            "form": form,
            "has_prior_booking": has_prior_booking,
        },
    )


@login_required
def booking_detail(request, booking_id):
    expire_pending_booking_requests()
    booking = get_object_or_404(
        BookingRequest.objects.select_related("guide_application"),
        pk=booking_id,
        traveler=request.user,
    )
    review = GuideReview.objects.filter(booking=booking).first()
    return render(
        request,
        "accounts/booking_detail.html",
        {"booking": booking, "review": review},
    )


@login_required
def guide_booking_requests(request):
    expire_pending_booking_requests()
    application = get_object_or_404(
        GuideApplication,
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    )
    booking_requests = BookingRequest.objects.filter(
        guide_application=application,
        status=BookingRequest.Status.PENDING,
    ).select_related("traveler")
    return render(
        request,
        "accounts/guide_booking_requests.html",
        {"booking_requests": booking_requests},
    )


@login_required
def guide_booking_request_detail(request, booking_id):
    expire_pending_booking_requests()
    booking = get_object_or_404(
        BookingRequest.objects.select_related("traveler", "guide_application"),
        pk=booking_id,
        guide_application__user=request.user,
        guide_application__status=GuideApplication.Status.VERIFIED,
    )
    return render(
        request,
        "accounts/guide_booking_request_detail.html",
        {"booking": booking},
    )


@login_required
@require_POST
def respond_to_booking_request(request, booking_id):
    """Accept or decline a pending request owned by the current guide.

    This is a POST-only action. Accepting rechecks date availability inside a
    transaction, reserves the dates, updates the booking, and notifies the
    traveler.
    """
    expire_pending_booking_requests()
    action = request.POST.get("action")
    if action not in {"accept", "decline"}:
        messages.error(request, "Choose accept or decline.")
        return redirect("accounts:guide_booking_request_detail", booking_id=booking_id)

    with transaction.atomic():
        booking = get_object_or_404(
            BookingRequest.objects.select_for_update().select_related(
                "traveler", "guide_application"
            ),
            pk=booking_id,
            guide_application__user=request.user,
            guide_application__status=GuideApplication.Status.VERIFIED,
        )
        if booking.status != BookingRequest.Status.PENDING:
            messages.error(request, "This request is no longer pending.")
            return redirect("accounts:guide_booking_request_detail", booking_id=booking.pk)

        if action == "accept":
            days = (booking.end_date - booking.start_date).days + 1
            available_days = list(
                GuideAvailability.objects.select_for_update()
                .filter(
                    guide_application=booking.guide_application,
                    available_date__gte=booking.start_date,
                    available_date__lte=booking.end_date,
                )
                .values_list("available_date", flat=True)
            )
            conflict = BookingRequest.objects.filter(
                guide_application=booking.guide_application,
                status=BookingRequest.Status.CONFIRMED,
                start_date__lte=booking.end_date,
                end_date__gte=booking.start_date,
            ).exclude(pk=booking.pk).exists()
            if len(available_days) != days or conflict:
                messages.error(
                    request,
                    "These dates are no longer available. The request remains pending so you can decline it.",
                )
                return redirect("accounts:guide_booking_request_detail", booking_id=booking.pk)
            booking.status = BookingRequest.Status.CONFIRMED
            booking.guide_application.availability_dates.filter(
                available_date__gte=booking.start_date,
                available_date__lte=booking.end_date,
            ).delete()
            subject = "Your guide accepted the booking request"
            message = (
                f"{booking.guide_application.full_name} accepted your request for "
                f"{booking.start_date} to {booking.end_date}. Please follow up with "
                "the guide about payment; online payment is not available in this version."
            )
            success_message = "Request accepted. The traveler was notified to follow up about payment."
        else:
            booking.status = BookingRequest.Status.DECLINED
            subject = "Your guide declined the booking request"
            message = (
                f"{booking.guide_application.full_name} declined your request for "
                f"{booking.start_date} to {booking.end_date}. The guide’s dates remain open."
            )
            success_message = "Request declined. The traveler was notified and the dates remain open."

        booking.responded_at = timezone.now()
        booking.save(update_fields=["status", "responded_at", "updated_at"])
        traveler_email = booking.traveler.email
        booking_pk = booking.pk

    sent = send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [traveler_email],
        fail_silently=True,
    )
    if not sent:
        logger.warning("Booking response notification could not be sent: booking_id=%s", booking_pk)
    messages.success(request, success_message)
    return redirect("accounts:guide_booking_request_detail", booking_id=booking_pk)


@login_required
def guide_trips(request):
    get_object_or_404(
        GuideApplication,
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    )
    bookings = BookingRequest.objects.filter(
        guide_application__user=request.user,
        guide_application__status=GuideApplication.Status.VERIFIED,
        status__in=[BookingRequest.Status.CONFIRMED, BookingRequest.Status.COMPLETED],
    ).select_related("traveler", "guide_application")
    return render(
        request,
        "accounts/guide_trips.html",
        {"bookings": bookings, "today": timezone.localdate()},
    )


@login_required
@require_POST
def complete_booking(request, booking_id):
    """Mark an ended, confirmed tour as complete for its assigned guide.

    Completion increments the guide's completed-tour count and enables the
    traveler to submit a review.
    """
    with transaction.atomic():
        booking = get_object_or_404(
            BookingRequest.objects.select_for_update().select_related("guide_application"),
            pk=booking_id,
            guide_application__user=request.user,
            guide_application__status=GuideApplication.Status.VERIFIED,
        )
        if booking.status != BookingRequest.Status.CONFIRMED:
            messages.error(request, "Only confirmed tours can be marked completed.")
            return redirect("accounts:guide_trips")
        if booking.end_date > timezone.localdate():
            messages.error(request, "A tour can be marked completed on or after its end date.")
            return redirect("accounts:guide_trips")
        booking.status = BookingRequest.Status.COMPLETED
        booking.completed_at = timezone.now()
        booking.save(update_fields=["status", "completed_at", "updated_at"])
        # Increment atomically without overwriting concurrent completion counts.
        GuideApplication.objects.filter(pk=booking.guide_application_id).update(
            completed_tours=F("completed_tours") + 1
        )

    messages.success(request, "Tour marked completed. The traveler can now leave a review.")
    return redirect("accounts:guide_trips")


@login_required
def submit_guide_review(request, booking_id):
    """Publish one review for the authenticated traveler's completed booking.

    A transaction prevents duplicate reviews and recalculates the guide's
    average rating and review count after a successful submission.
    """
    booking = get_object_or_404(
        BookingRequest.objects.select_related("guide_application"),
        pk=booking_id,
        traveler=request.user,
    )
    if booking.status != BookingRequest.Status.COMPLETED:
        messages.error(request, "You can review a guide after the tour is completed.")
        return redirect("accounts:booking_detail", booking_id=booking.pk)
    if GuideReview.objects.filter(booking=booking).exists():
        messages.info(request, "You have already reviewed this booking.")
        return redirect("accounts:guide_reviews", guide_id=booking.guide_application_id)

    form = GuideReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            booking = BookingRequest.objects.select_for_update().get(pk=booking.pk)
            if booking.status != BookingRequest.Status.COMPLETED:
                form.add_error(None, "Only completed tours can be reviewed.")
            elif GuideReview.objects.filter(booking=booking).exists():
                messages.info(request, "You have already reviewed this booking.")
                return redirect("accounts:guide_reviews", guide_id=booking.guide_application_id)
            else:
                guide = GuideApplication.objects.select_for_update().get(
                    pk=booking.guide_application_id
                )
                GuideReview.objects.create(
                    booking=booking,
                    guide_application=guide,
                    rating=form.cleaned_data["rating"],
                    review_text=form.cleaned_data["review_text"].strip(),
                )
                totals = GuideReview.objects.filter(guide_application=guide).aggregate(
                    average=Avg("rating"), count=Count("pk")
                )
                guide.average_rating = Decimal(str(totals["average"])).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                )
                guide.review_count = totals["count"]
                guide.save(update_fields=["average_rating", "review_count"])
        if not form.errors:
            messages.success(request, "Your review was published.")
            return redirect("accounts:guide_reviews", guide_id=booking.guide_application_id)

    return render(
        request,
        "accounts/guide_review_form.html",
        {"booking": booking, "form": form},
    )


def guide_reviews(request, guide_id):
    guide = get_object_or_404(
        GuideApplication.objects.filter(status=GuideApplication.Status.VERIFIED),
        pk=guide_id,
    )
    reviews = guide.reviews.select_related("booking").all()
    return render(
        request,
        "accounts/guide_reviews.html",
        {"guide": guide, "reviews": reviews},
    )


@login_required
def guide_received_reviews(request):
    guide = get_object_or_404(
        GuideApplication,
        user=request.user,
        status=GuideApplication.Status.VERIFIED,
    )
    reviews = guide.reviews.select_related("booking", "booking__traveler").all()
    return render(
        request,
        "accounts/guide_received_reviews.html",
        {"guide": guide, "reviews": reviews},
    )


@login_required
@require_POST
def reply_to_guide_review(request, review_id):
    form = GuideReplyForm(request.POST)
    review = get_object_or_404(
        GuideReview.objects.select_related("guide_application"),
        pk=review_id,
        guide_application__user=request.user,
        guide_application__status=GuideApplication.Status.VERIFIED,
    )
    if review.guide_reply:
        messages.error(request, "A reply has already been posted for this review.")
    elif form.is_valid():
        with transaction.atomic():
            review = GuideReview.objects.select_for_update().get(pk=review.pk)
            if review.guide_reply:
                messages.error(request, "A reply has already been posted for this review.")
            else:
                review.guide_reply = form.cleaned_data["guide_reply"].strip()
                review.guide_replied_at = timezone.now()
                review.save(update_fields=["guide_reply", "guide_replied_at"])
                messages.success(request, "Your public reply was posted.")
    else:
        messages.error(request, "Enter a reply of at least two characters.")
    return redirect("accounts:guide_received_reviews")
