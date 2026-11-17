from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import EmailLoginForm, PasswordResetSetForm, VerifiedPasswordResetForm

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("verify/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=EmailLoginForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            form_class=VerifiedPasswordResetForm,
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
            form_class=PasswordResetSetForm,
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.edit_profile, name="edit_profile"),
    path("guides/<int:guide_id>/book/", views.book_guide, name="book_guide"),
    path("bookings/<int:booking_id>/", views.booking_detail, name="booking_detail"),
    path("guide/bookings/", views.guide_booking_requests, name="guide_booking_requests"),
    path("guide/bookings/<int:booking_id>/", views.guide_booking_request_detail, name="guide_booking_request_detail"),
    path("guide/bookings/<int:booking_id>/respond/", views.respond_to_booking_request, name="respond_to_booking_request"),
    path("guide/trips/", views.guide_trips, name="guide_trips"),
    path("guide/availability/", views.manage_guide_availability, name="manage_guide_availability"),
    path("guide/availability/<int:availability_id>/remove/", views.remove_guide_availability, name="remove_guide_availability"),
    path("guide/trips/<int:booking_id>/complete/", views.complete_booking, name="complete_booking"),
    path("bookings/<int:booking_id>/review/", views.submit_guide_review, name="submit_guide_review"),
    path("guides/<int:guide_id>/reviews/", views.guide_reviews, name="guide_reviews"),
    path("guide/reviews/", views.guide_received_reviews, name="guide_received_reviews"),
    path("guide/reviews/<int:review_id>/reply/", views.reply_to_guide_review, name="reply_to_guide_review"),
    path("guide/apply/", views.apply_as_guide, name="apply_as_guide"),
    path("admin/guide-applications/", views.guide_application_list, name="guide_application_list"),
    path("admin/guide-applications/<int:application_id>/", views.guide_application_review, name="guide_application_review"),
    path("admin/guide-applications/<int:application_id>/files/<str:document_type>/", views.guide_application_document, name="guide_application_document"),
]
