"""Post monthly employee salaries as operating expenses (run on the 1st via cron)."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts_core.models import Employee
from accounts_core.salary_expense import parse_salary_month, pay_employee_salary, salary_expense_exists, salary_period_key


class Command(BaseCommand):
    help = "Post active employee salaries for a calendar month (skips months already paid manually)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Target month as YYYY-MM (default: current calendar month).",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        month_str = options.get("month")
        if month_str:
            year, mon = parse_salary_month(month_str)
        else:
            year, mon = today.year, today.month
        period_key = salary_period_key(year, mon)

        created = 0
        skipped = 0
        errors = 0
        employees = Employee.objects.filter(is_active=True, monthly_salary__gt=Decimal("0"))
        with transaction.atomic():
            for emp in employees:
                if salary_expense_exists(emp, period_key):
                    skipped += 1
                    continue
                try:
                    pay_employee_salary(emp, year, mon, user=None)
                    created += 1
                except ValueError as exc:
                    errors += 1
                    self.stdout.write(self.style.WARNING(f"{emp.name}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Salaries for {period_key}: {created} posted, {skipped} skipped (already paid), {errors} errors."
            )
        )
