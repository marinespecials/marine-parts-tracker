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
  (`collectstatic` is required: the new look lives in `static/css/app.css` and `static/js/app.js`.)
- Set the environment variable `SECRET_KEY` to a long random string (do not rely on the built-in default).
- Leave `DEBUG` unset (defaults to off).

## Keeping the free Render plan awake
Render's free plan sleeps after ~15 minutes without visitors, so the first visit takes 30-60 s.
`/healthz/` is a tiny public page that answers `ok` without touching the database.
Point a free uptime monitor (e.g. UptimeRobot, "HTTP(s)" monitor, every 5-10 minutes) at:
`https://marine-specials-tracker.onrender.com/healthz/`
The database (Neon) is deliberately not woken by this, so it doesn't use up Neon's free compute hours.

## Part categories
All parts share one category list (`PART_CATEGORIES` in `tracker/models.py`).
New parts are auto-categorised from their name; on the Warehouse page,
"Auto-sort uncategorised" sorts existing General parts on demand. Edit any part to change it.
