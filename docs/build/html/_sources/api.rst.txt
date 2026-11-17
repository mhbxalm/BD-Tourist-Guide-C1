Python API Reference
====================

The API reference below is generated from Python docstrings in the project
source. Update the docstring when behavior changes, then rebuild the HTML docs.

Booking expiry service
----------------------

.. autofunction:: accounts.services.expire_pending_booking_requests

Guide search
------------

.. autofunction:: accounts.views.guide_search_context

Public homepage
---------------

.. autofunction:: accounts.views.home

Dashboard
---------

.. autofunction:: accounts.views.dashboard

Registration and verification
-----------------------------

.. autofunction:: accounts.views.register

.. autofunction:: accounts.views.verify_email

Guide application
-----------------

.. autofunction:: accounts.views.apply_as_guide

.. autofunction:: accounts.views.guide_application_review

Booking workflows
-----------------

.. autofunction:: accounts.views.book_guide

.. autofunction:: accounts.views.respond_to_booking_request

.. autofunction:: accounts.views.complete_booking

Reviews
-------

.. autofunction:: accounts.views.submit_guide_review

Core domain models
------------------

.. autoclass:: accounts.models.User
   :members: is_temporarily_locked

.. autoclass:: accounts.models.GuideApplication

.. autoclass:: accounts.models.BookingRequest
   :members: number_of_days, expires_at

.. autoclass:: accounts.models.GuideReview

.. autoclass:: accounts.models.GuideDecisionLog

Forms
-----

.. autoclass:: accounts.forms.GuideApplicationForm

.. autoclass:: accounts.forms.GuideSearchForm

.. autoclass:: accounts.forms.GuideBookingRequestForm

.. autoclass:: accounts.forms.GuideReviewForm
