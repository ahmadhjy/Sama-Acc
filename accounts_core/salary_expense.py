"""Shared helpers for employee salary operating expenses."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from accounts_core.models import Employee
from expenses.models import OperatingExpense
from purchases.models import ExpenseCategory

SALARY_CATEGORY_CODE = "SALARY"


def salary_period_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def parse_salary_month(value: str) -> tuple[int, int]:
    """Parse YYYY-MM from HTML month input."""
    raw = (value or "").strip()
    if not raw or "-" not in raw:
        raise ValueError("Select a salary month (YYYY-MM).")
    year_str, month_str = raw.split("-", 1)
    year, month = int(year_str), int(month_str)
    if month < 1 or month > 12:
        raise ValueError("Invalid salary month.")
    return year, month


def salary_expense_description(employee: Employee, period_key: str) -> str:
    return f"Salary {employee.name} ({period_key})"


def get_salary_category() -> ExpenseCategory:
    cat, _ = ExpenseCategory.objects.get_or_create(
        code=SALARY_CATEGORY_CODE,
        defaults={"name": "Salaries", "is_active": True},
    )
    return cat


def salary_expense_exists(employee: Employee, period_key: str) -> bool:
    desc = salary_expense_description(employee, period_key)
    return OperatingExpense.objects.filter(description=desc).exclude(
        status=OperatingExpense.Status.VOIDED
    ).exists()


def pay_employee_salary(employee: Employee, year: int, month: int, user=None) -> OperatingExpense:
    if not employee.is_active:
        raise ValueError("Employee is not active.")
    if (employee.monthly_salary or Decimal("0")) <= Decimal("0"):
        raise ValueError("Set a monthly salary before paying.")
    period_key = salary_period_key(year, month)
    if salary_expense_exists(employee, period_key):
        raise ValueError(f"Salary for {period_key} is already recorded for this employee.")
    expense_date = date(year, month, monthrange(year, month)[1])
    opex = OperatingExpense.objects.create(
        category=get_salary_category(),
        expense_date=expense_date,
        currency="USD",
        amount=employee.monthly_salary,
        amount_usd=employee.monthly_salary,
        description=salary_expense_description(employee, period_key),
        status=OperatingExpense.Status.DRAFT,
    )
    opex.post(user)
    return opex
