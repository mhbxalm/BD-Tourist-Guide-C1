from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count
from django.utils import timezone

from accounts.models import (
    BookingRequest,
    GuideApplication,
    GuideAvailability,
    GuideReview,
    User,
)

SAMPLE_RATINGS = [
    [5, 5, 4],
    [5, 5, 5],
    [5, 4, 5],
    [5, 5, 4],
    [4, 5, 5],
    [4, 4, 5],
    [4, 4, 5],
    [5, 4, 5],
]
SAMPLE_REVIEW_TEXTS = [
    "The guide was welcoming and shared helpful local context throughout the trip.",
    "The meeting details were clear and the pace felt comfortable. I enjoyed the tour.",
    "A thoughtful guide with great local knowledge. I would recommend this experience.",
]


DEMO_GUIDES = [
    {
        "slug": "afsana-rahman",
        "full_name": "Afsana Rahman",
        "bio": "A Cox’s Bazar local who enjoys sharing quiet beach walks, seafood spots, and the best sunset viewpoints.",
        "languages": "Bangla, English",
        "areas_covered": "Cox’s Bazar, Inani Beach, Himchari",
        "specialties": "Beach walks, food, nature",
        "daily_rate": "2800.00",
        "max_group_size": 8,
        "average_rating": "4.8",
        "review_count": 38,
        "completed_tours": 86,
        "weekdays": {1, 3, 4, 5, 6},
    },
    {
        "slug": "shahriar-hossain",
        "full_name": "Shahriar Hossain",
        "bio": "I lead relaxed day trips around Sylhet, from tea estates and river views to local markets and regional food.",
        "languages": "Bangla, English",
        "areas_covered": "Sylhet, Sreemangal, Jaflong",
        "specialties": "Tea gardens, food, photography",
        "daily_rate": "3200.00",
        "max_group_size": 6,
        "average_rating": "4.9",
        "review_count": 52,
        "completed_tours": 104,
        "weekdays": {0, 2, 3, 5},
    },
    {
        "slug": "maria-chakma",
        "full_name": "Maria Chakma",
        "bio": "A hill-country guide focused on Bandarban’s landscapes, local culture, and comfortable, responsible day hikes.",
        "languages": "Bangla, English, Chakma",
        "areas_covered": "Bandarban, Nilgiri, Meghla",
        "specialties": "Hiking, culture, nature",
        "daily_rate": "3600.00",
        "max_group_size": 5,
        "average_rating": "4.7",
        "review_count": 24,
        "completed_tours": 61,
        "weekdays": {1, 2, 4, 5},
    },
    {
        "slug": "aminul-islam",
        "full_name": "Aminul Islam",
        "bio": "I help visitors explore the Sundarbans with a focus on its waterways, wildlife, and conservation stories.",
        "languages": "Bangla, English",
        "areas_covered": "Sundarbans, Khulna, Mongla",
        "specialties": "Wildlife, boat tours, nature",
        "daily_rate": "4500.00",
        "max_group_size": 8,
        "average_rating": "4.9",
        "review_count": 31,
        "completed_tours": 73,
        "weekdays": {0, 1, 3, 6},
    },
    {
        "slug": "nabila-sultana",
        "full_name": "Nabila Sultana",
        "bio": "A history enthusiast offering friendly walks through Old Dhaka’s architecture, stories, markets, and street food.",
        "languages": "Bangla, English",
        "areas_covered": "Old Dhaka, Lalbagh, Ahsan Manzil",
        "specialties": "History, architecture, food",
        "daily_rate": "2200.00",
        "max_group_size": 10,
        "average_rating": "4.6",
        "review_count": 44,
        "completed_tours": 118,
        "weekdays": {0, 1, 2, 3, 4, 5},
    },
    {
        "slug": "rifat-uddin",
        "full_name": "Rifat Uddin",
        "bio": "I guide small groups through Sreemangal’s tea country, forest trails, and nearby villages at an easy pace.",
        "languages": "Bangla, English",
        "areas_covered": "Sreemangal, Sylhet, Lawachara",
        "specialties": "Tea gardens, wildlife, hiking",
        "daily_rate": "3000.00",
        "max_group_size": 6,
        "average_rating": "4.5",
        "review_count": 17,
        "completed_tours": 39,
        "weekdays": {0, 2, 4, 5},
    },
    {
        "slug": "tahmina-akhtar",
        "full_name": "Tahmina Akhtar",
        "bio": "A local host for Cox’s Bazar who plans easygoing trips around the coast, local crafts, and family-friendly stops.",
        "languages": "Bangla, English",
        "areas_covered": "Cox’s Bazar, Ramu, Inani Beach",
        "specialties": "Family tours, culture, beach walks",
        "daily_rate": "2500.00",
        "max_group_size": 7,
        "average_rating": "4.4",
        "review_count": 12,
        "completed_tours": 28,
        "weekdays": {0, 2, 4, 5, 6},
    },
    {
        "slug": "bikash-tanchangya",
        "full_name": "Bikash Tanchangya",
        "bio": "A Bandarban-based guide sharing mountain viewpoints, local food, and practical advice for day hikes.",
        "languages": "Bangla, English, Tanchangya",
        "areas_covered": "Bandarban, Nilachal, Chimbuk",
        "specialties": "Adventure, hiking, photography",
        "daily_rate": "3400.00",
        "max_group_size": 5,
        "average_rating": "4.8",
        "review_count": 29,
        "completed_tours": 66,
        "weekdays": {1, 3, 4, 6},
    },
]


class Command(BaseCommand):
    help = "Create or refresh sample guide profiles and availability for local development."

    def handle(self, *args, **options):
        today = timezone.localdate()
        created_count = 0
        updated_count = 0
        for guide_data in DEMO_GUIDES:
            data = guide_data.copy()
            slug = data.pop("slug")
            weekdays = data.pop("weekdays")
            email = f"{slug}@demo.bdtouristguide.invalid"
            user, user_created = User.objects.get_or_create(
                username=f"demo-{slug}",
                defaults={
                    "email": email,
                    "first_name": data["full_name"].split()[0],
                    "last_name": " ".join(data["full_name"].split()[1:]),
                    "role": User.Role.GUIDE,
                    "is_email_verified": True,
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            else:
                user.email = email
                user.role = User.Role.GUIDE
                user.is_email_verified = True
                user.save(update_fields=["email", "role", "is_email_verified"])

            application = GuideApplication.objects.filter(
                user=user, is_demo=True
            ).first()
            defaults = {
                **data,
                "status": GuideApplication.Status.VERIFIED,
                "is_demo": True,
                "profile_photo": "",
                "id_document": "",
                "license_document": "",
                "rejection_reason": "",
            }
            if application:
                for field, value in defaults.items():
                    setattr(application, field, value)
                application.save()
                updated_count += 1
            else:
                application = GuideApplication.objects.create(user=user, **defaults)
                created_count += 1

            application.availability_dates.filter(available_date__lt=today).delete()
            availability = [
                GuideAvailability(
                    guide_application=application,
                    available_date=today + timedelta(days=offset),
                )
                for offset in range(1, 91)
                if (today + timedelta(days=offset)).weekday() in weekdays
            ]
            GuideAvailability.objects.bulk_create(availability, ignore_conflicts=True)

            guide_index = next(
                index
                for index, item in enumerate(DEMO_GUIDES)
                if item["slug"] == slug
            )
            for review_index, rating in enumerate(SAMPLE_RATINGS[guide_index]):
                traveler_username = f"demo-reviewer-{slug}-{review_index + 1}"
                traveler_email = f"{traveler_username}@demo.bdtouristguide.invalid"
                traveler, traveler_created = User.objects.get_or_create(
                    username=traveler_username,
                    defaults={
                        "email": traveler_email,
                        "first_name": f"Traveler {review_index + 1}",
                        "role": User.Role.TRAVELER,
                        "is_email_verified": True,
                    },
                )
                if traveler_created:
                    traveler.set_unusable_password()
                    traveler.save(update_fields=["password"])
                tour_date = today - timedelta(days=45 + review_index * 12)
                booking, _ = BookingRequest.objects.get_or_create(
                    traveler=traveler,
                    guide_application=application,
                    start_date=tour_date,
                    end_date=tour_date,
                    defaults={
                        "group_size": 2,
                        "meeting_place": "Agreed meeting point",
                        "notes": "Sample completed tour for local development.",
                        "daily_rate_snapshot": application.daily_rate,
                        "total_price": application.daily_rate,
                        "status": BookingRequest.Status.COMPLETED,
                        "responded_at": timezone.now(),
                        "completed_at": timezone.now(),
                    },
                )
                GuideReview.objects.get_or_create(
                    booking=booking,
                    defaults={
                        "guide_application": application,
                        "rating": rating,
                        "review_text": SAMPLE_REVIEW_TEXTS[review_index],
                    },
                )

            rating_summary = GuideReview.objects.filter(
                guide_application=application
            ).aggregate(average=Avg("rating"), count=Count("pk"))
            application.average_rating = round(rating_summary["average"], 1)
            application.review_count = rating_summary["count"]
            application.save(update_fields=["average_rating", "review_count"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo guides ready: {created_count} created, {updated_count} refreshed."
            )
        )
