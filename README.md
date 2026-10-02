# Marine Parts Tracker

Django app for orders, warehouse stock, invoices and purchasing.

## Run locally (Windows)
1. Install Python 3.12 or newer.
2. Double-click `start_server.bat`. First run creates the `venv`, installs requirements,
   backs up and migrates the database, and starts the server on port 8000.
3. First time only, create your login: `venv\Scripts\activate` then `python manage.py createsuperuser`.

## Everyday commands
- Backup now: `python manage.py backup_db` (copies go in `backups/`, newest 14 kept)
- Run the tests: `python manage.py test`
- Change `.env`-style settings with environment variables: `DEBUG`, `SECRET_KEY`,
  `ALLOWED_HOSTS_EXTRA`, `REQUIRE_LOGIN`, `DATABASE_URL`.

## Deploying on Render
- Build command must include: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- Set the environment variable `SECRET_KEY` to a long random string (do not rely on the built-in default).
- Leave `DEBUG` unset (defaults to off).
