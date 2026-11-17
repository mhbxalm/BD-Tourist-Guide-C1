Data Model
==========

The ``accounts`` app uses Django's relational ORM. The custom ``User`` model is
configured as ``AUTH_USER_MODEL``. Foreign keys connect related workflow
records, while database constraints protect important uniqueness rules.

.. list-table:: Core models
   :header-rows: 1

   * - Model
     - Important relationships and data
     - Purpose
   * - ``User``
     - Unique email, role, verification and lockout state.
     - Authentication and account state.
   * - ``GuideApplication``
     - Belongs to a user; includes profile, rates, uploaded documents, and review status.
     - Guide profile and approval workflow.
   * - ``GuideAvailability``
     - Belongs to a guide application; unique per guide and date.
     - Dates when the guide is available.
   * - ``BookingRequest``
     - Connects a traveler and guide; stores date range, rate snapshot, total, and timestamps.
     - Request status, group size, meeting place, and trip price.
   * - ``GuideReview``
     - One-to-one with a booking; belongs to a guide.
     - Traveler rating, review text, and guide reply.
   * - ``GuideDecisionLog``
     - Connects an application and administrator.
     - Audit trail for approval or rejection.

The booking status values are pending, confirmed, declined, expired, and
completed. The guide application states are pending review, verified, and
rejected. A booking's one-to-one relationship with ``GuideReview`` limits each
booking to one review.

Important rules
---------------

* Guide daily rates must be at least 1 BDT.
* Guide group size is limited to 1–100 travelers.
* Review ratings are from 1 to 5.
* A guide cannot have duplicate availability records for the same date.
* Users and guides referenced by booking history are protected from deletion
  where the relationship uses ``on_delete=PROTECT``.
