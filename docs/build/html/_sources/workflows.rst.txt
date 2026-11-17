User Workflows
==============

Browse and search
-----------------

Visitors can browse the homepage and search verified guides without signing in.
The shared search context filters by destination, date, language, specialty,
daily price range, and minimum rating. Results can be ordered by rating, price,
or completed tours.

Registration and email verification
------------------------------------

#. A visitor submits an email address, name, and password through the
   registration form.
#. Django validates the input and creates a traveler account whose email is
   not yet verified.
#. The application sends a time-sensitive verification link. In development,
   the console email backend prints the link in the ``runserver`` terminal.
#. A valid link marks the address as verified. Invalid or expired tokens are
   rejected.
#. Unverified users can continue to browse; booking requests require verified
   email.

Guide application and administrator review
-------------------------------------------

#. An authenticated user submits a guide profile, photo, and identity document.
#. The application is stored in the ``pending`` state.
#. An administrator can view the submitted records and protected documents.
#. The administrator approves or rejects the application. Each decision is
   written to ``GuideDecisionLog`` with the administrator and decision time.
#. Only verified guide applications appear in public search and accept booking
   requests.

Booking lifecycle
-----------------

.. code-block:: text

   PENDING --guide accepts--> CONFIRMED --guide completes trip--> COMPLETED
      |                            |
      +--guide declines--> DECLINED
      +--24-hour timeout--> EXPIRED

Before a request is saved, the application checks the traveler's email status,
guide verification, date range, per-date availability, group-size limit, and
conflicting requests. It stores a price snapshot so later rate changes do not
change an existing booking. The guide accepts or declines a pending request;
the traveler receives a notification.

After completion, the traveler may submit one review for the booking. The
application updates the guide's average rating and review count. A guide may
then post one public reply to that review.

Request expiry
--------------

Pending requests expire after 24 hours. The expiry service rechecks each
candidate inside a database transaction before changing its status and
notifying the traveler. Dashboard and booking-page visits process overdue
requests. For unattended processing, schedule:

.. code-block:: console

   python manage.py expire_booking_requests
