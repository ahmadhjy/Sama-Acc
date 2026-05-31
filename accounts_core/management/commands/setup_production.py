"""One-time production bootstrap after migrate."""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run migrate, seed_roles, and collectstatic for production (safe to re-run)."

    def handle(self, *args, **options):
        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    "DEBUG is True. For production, use DJANGO_SETTINGS_MODULE=config.settings.production"
                )
            )

        self.stdout.write("Running migrations...")
        call_command("migrate", interactive=False, verbosity=1)

        self.stdout.write("Seeding roles (Admin, Accounting, Sales)...")
        call_command("seed_roles", verbosity=1)

        self.stdout.write("Collecting static files...")
        call_command("collectstatic", interactive=False, verbosity=1)

        self.stdout.write(self.style.SUCCESS("Production bootstrap complete."))
        self.stdout.write(
            "Next steps:\n"
            "  1. python manage.py createsuperuser\n"
            "  2. Reload the web app on PythonAnywhere\n"
            "  3. Log in and verify Admin → Company branding"
        )
