"""Post monthly employee salaries as operating expenses (run at month end via cron)."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts_core.models import Employee
from expenses.models import OperatingExpense
from purchases.models import ExpenseCategory


class Command(BaseCommand):
    help = "Create draft operating expenses for active employee monthly salaries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Target month as YYYY-MM (default: previous calendar month).",
        )
        parser.add_argument(
            "--post",
            action="store_true",
            help="Post expenses immediately after creation.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        month_str = options.get("month")
        if month_str:
            year, mon = map(int, month_str.split("-"))
        else:
            if today.month == 1:
                year, mon = today.year - 1, 12
            else:
                year, mon = today.year, today.month - 1
        last_day = monthrange(year, mon)[1]
        expense_date = date(year, mon, last_day)
        period_key = f"{year}-{mon:02d}"

        cat, _ = ExpenseCategory.objects.get_or_create(
            code="SALARY",
            defaults={"name": "Salaries", "is_active": True},
        )

        created = 0
        skipped = 0
        employees = Employee.objects.filter(is_active=True, monthly_salary__gt=Decimal("0"))
        with transaction.atomic():
            for emp in employees:
                desc = f"Salary {emp.name} ({period_key})"
                if OperatingExpense.objects.filter(description=desc).exists():
                    skipped += 1
                    continue
                opex = OperatingExpense.objects.create(
                    category=cat,
                    expense_date=expense_date,
                    currency="USD",
                    amount=emp.monthly_salary,
                    amount_usd=emp.monthly_salary,
                    description=desc,
                    status=OperatingExpense.Status.DRAFT,
                )
                if options.get("post"):
                    opex.post(user=None)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Salaries for {period_key}: {created} created, {skipped} skipped (already exist)."
            )
        )
