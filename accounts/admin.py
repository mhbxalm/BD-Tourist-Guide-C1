from django.contrib import admin

from .models import (
    BookingRequest,
    GuideApplication,
    GuideAvailability,
    GuideDecisionLog,
    GuideReview,
    User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "is_email_verified", "is_staff", "is_active")
    list_filter = ("role", "is_email_verified", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")


@admin.register(GuideApplication)
class GuideApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "user",
        "status",
        "is_demo",
        "daily_rate",
        "average_rating",
        "created_at",
        "reviewed_by",
    )
    list_filter = ("status", "is_demo", "created_at")
    search_fields = ("full_name", "user__email", "areas_covered")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")


@admin.register(GuideAvailability)
class GuideAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("guide_application", "available_date")
    list_filter = ("available_date",)
    search_fields = ("guide_application__full_name", "guide_application__areas_covered")


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "traveler",
        "guide_application",
        "start_date",
        "end_date",
        "status",
        "completed_at",
        "total_price",
    )
    list_filter = ("status", "start_date")
    search_fields = ("traveler__email", "guide_application__full_name")
    readonly_fields = (
        "created_at",
        "updated_at",
        "responded_at",
        "completed_at",
        "daily_rate_snapshot",
        "total_price",
    )


@admin.register(GuideReview)
class GuideReviewAdmin(admin.ModelAdmin):
    list_display = ("guide_application", "booking", "rating", "created_at", "guide_replied_at")
    list_filter = ("rating", "created_at")
    search_fields = ("guide_application__full_name", "review_text")
    readonly_fields = (
        "booking",
        "guide_application",
        "rating",
        "review_text",
        "guide_reply",
        "created_at",
        "guide_replied_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(GuideDecisionLog)
class GuideDecisionLogAdmin(admin.ModelAdmin):
    list_display = ("application", "administrator", "decision", "decided_at")
    list_filter = ("decision", "decided_at")
    readonly_fields = ("application", "administrator", "decision", "reason", "decided_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
