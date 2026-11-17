# BD Tourist Guide

Django web application for connecting travelers with verified local guides in Bangladesh.

## Stack

- Python 3 and Django (MTV architecture)
- Django templates, HTML, CSS, JavaScript, and Bootstrap
- SQLite by default; optional MySQL database settings via environment variables
- PEP 8, Black, and Ruff

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py makemigrations accounts
python manage.py migrate
python manage.py seed_demo_guides
python manage.py runserver
```

The development email backend prints verification messages and links in the `runserver` terminal. Set `DJANGO_SECRET_KEY` and configure a production email backend before deployment. The current registration flow verifies email; SMS/phone verification needs an SMS provider integration.

## Run on another computer

Clone the GitHub repository and open a terminal in the project directory:

```sh
git clone <repository-url>
cd BD_Tourist_Guide
```

Create and activate a fresh virtual environment. On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Then install dependencies, create the database tables, load sample guides, and start the server:

```sh
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_guides
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in a browser. The SQLite database is not included in the repository; migrations create a new one, and `seed_demo_guides` adds the sample guide profiles.

## Documentation

The project documentation is built with Sphinx from reStructuredText pages and Python docstrings. With the virtual environment activated, install all project dependencies and build the HTML documentation:

```sh
python -m pip install -r requirements.txt
sphinx-build -b html docs/source docs/build/html
```

Open `docs/build/html/index.html` in a browser. The Sphinx source lives in `docs/source/`; generated files under `docs/build/` are excluded from Git. Python docstrings use Google-style `Args` and `Returns` sections, rendered by Sphinx Napoleon and included with Autodoc.

For MySQL, install `mysqlclient`, set `DB_ENGINE=mysql`, and provide `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`.

## Current feature

- Traveler registration with email uniqueness and password validation
- Signed email verification links
- Login and logout with role-ready account foundation
- Temporary login lock after 5 consecutive failures (15 minutes)
- Password reset links for verified email addresses (single-use, 30 minutes)
- Guide application form with profile details and protected ID uploads
- Administrator approval/rejection workflow with decision audit records
- Demo guide profiles with rotating 90-day availability schedules
- Working guide search by destination, date, language, specialty, price range, and rating
- Sorting by rating, price, or completed tours
- Traveler booking requests with date-range availability, group-size checks, price summaries, and guide notification
- Guide inbox to accept or decline pending requests, with traveler notifications
- Automatic 24-hour request expiry when pages are accessed, plus a scheduled management command
- Guide tour completion, one traveler review per completed booking, guide rating averages, and one public guide reply per review
- Guide self-service availability calendar to add or remove open dates

Demo profiles are labeled in search results and use reserved `.invalid` email addresses. They are sample data only; replace them with verified real applications before launch. Re-running `seed_demo_guides` refreshes the sample profiles and future availability without creating duplicate records.

For unattended 24-hour expiry, schedule `python manage.py expire_booking_requests` to run hourly (or more frequently) in the deployment environment. Dashboard and booking page visits also process overdue requests.
