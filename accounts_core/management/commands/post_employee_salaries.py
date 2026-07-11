"""Post monthly employee salaries as operating expenses (run on the 1st via cron)."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Disabled — record salaries manually as operating expenses."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Automatic salary posting is disabled. "
                "Add employee salaries from Operating Expenses in the app."
            )
        )
