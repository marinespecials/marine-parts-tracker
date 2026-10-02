"""Safe copy of the SQLite database.   Usage:  python manage.py backup_db

Uses SQLite's own backup API, so it is safe to run while the server is running.
Keeps the newest 14 copies in the ./backups folder.
"""
import sqlite3
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

KEEP = 14


class Command(BaseCommand):
    help = 'Back up the SQLite database into the backups/ folder.'

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if 'sqlite' not in db['ENGINE']:
            self.stdout.write('Not using SQLite - use your database host\'s backups instead.')
            return
        source_path = str(db['NAME'])
        folder = settings.BASE_DIR / 'backups'
        folder.mkdir(exist_ok=True)
        target = folder / f"db-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"

        src = sqlite3.connect(source_path)
        dst = sqlite3.connect(str(target))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        for old in sorted(folder.glob('db-*.sqlite3'))[:-KEEP]:
            old.unlink()
        self.stdout.write(self.style.SUCCESS(f'Backup written: {target}'))
