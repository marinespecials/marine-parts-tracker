@echo off
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo venv missing - creating it...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)
set DEBUG=True
python manage.py backup_db
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000
