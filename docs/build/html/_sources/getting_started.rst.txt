Getting Started
===============

Requirements
------------

The project is implemented with Python 3 and Django 5.2. SQLite is used by
default for local development. Sphinx 9 is included in ``requirements.txt``
for building the documentation.

Install the application and documentation dependencies from the project root:

.. code-block:: console

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python manage.py migrate

Run the application:

.. code-block:: console

   python manage.py runserver

The development email backend prints verification and notification messages in
the server terminal.

Build the documentation
-----------------------

With the virtual environment activated, run this command from the project
root:

.. code-block:: console

   sphinx-build -b html docs/source docs/build/html

Open ``docs/build/html/index.html`` in a browser to browse the generated
documentation. Re-run the build after changing documentation pages or Python
docstrings. The generated files are kept under ``docs/build/`` and are ignored
by Git; the source pages and Sphinx configuration remain version controlled.

Documentation format
--------------------

Project narrative pages use reStructuredText (``.rst``). Python APIs are
included from source docstrings by Sphinx Autodoc. Docstrings use Google-style
sections such as ``Args`` and ``Returns``; Sphinx Napoleon converts those
sections into formatted documentation.

MySQL configuration
-------------------

To use MySQL instead of SQLite, install ``mysqlclient`` and set
``DB_ENGINE=mysql``, ``DB_NAME``, ``DB_USER``, ``DB_PASSWORD``, ``DB_HOST``, and
``DB_PORT`` in the environment before running Django commands.
