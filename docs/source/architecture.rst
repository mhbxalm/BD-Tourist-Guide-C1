Architecture
============

Architectural pattern
---------------------

The application uses Django's Model-Template-View (MTV) architecture, Django's
version of an MVC-style pattern. Models define relational data and domain
state. Views coordinate requests, permissions, forms, and workflow operations.
Templates render HTML responses. URL configurations connect incoming paths to
views. Django forms validate input, and ``accounts.services`` contains reusable
booking-expiry logic.

Component responsibilities
---------------------------

=========================  ================================================
Component                  Project responsibility
=========================  ================================================
``accounts.models``        User, guide, availability, booking, review, and
                           administrator-decision data.
``accounts.forms``         Input parsing, validation, normalization, and form
                           widgets.
``accounts.views``         HTTP request handling, access checks, workflows,
                           and response selection.
``accounts.services``      Reusable business operation for expiring requests.
``accounts.urls``          Named account routes for registration, booking,
                           guide management, and reviews.
``templates/``             Shared layout and feature-specific HTML pages.
``config/settings.py``     Django apps, middleware, templates, authentication,
                           database, email, and static/media configuration.
=========================  ================================================

Request lifecycle
-----------------

.. code-block:: text

   Browser
     -> Django URL resolver
     -> View (authentication, authorization, workflow)
     -> Form validation
     -> ORM models / reusable service
     -> SQLite by default, or configured MySQL
     -> View
     -> Django template or redirect
     -> Browser

The Django middleware stack provides sessions, authentication, messages,
localization, CSRF protection, and common HTTP handling. HTML is rendered on
the server using Django templates, Bootstrap, and the project's CSS.

Why MTV fits this project
-------------------------

The project is composed of relational workflows: email verification, guide
approval, date availability, booking requests, trip completion, and reviews.
Django's ORM and forms represent these workflows directly, and server-rendered
templates keep the current interface in one application without a separate
frontend API. This structure also makes each concern easier to locate as
features change.
