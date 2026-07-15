from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient
from django.test import TestCase
from django.urls import reverse

from accounts_core.models import Currency
from expenses.models import OperatingExpense
from purchases.models import ExpenseCategory


class OperatingExpenseEditDeleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="opex1", password="test12345")
        self.http = HttpClient()
        self.http.force_login(self.user)
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        self.category = ExpenseCategory.objects.create(code="RENT", name="Rent", is_active=True)
        self.expense = OperatingExpense.objects.create(
            expense_no="OPEX-2026-0001",
            category=self.category,
            expense_date=date(2026, 7, 1),
            currency="USD",
            amount=Decimal("500.00"),
            amount_usd=Decimal("500.00"),
            description="Office rent",
            status=OperatingExpense.Status.POSTED,
        )

    def test_posted_expense_can_be_edited_from_app(self):
        url = reverse("expenses:expense_edit", args=[self.expense.id])
        resp = self.http.get(url)
        self.assertEqual(resp.status_code, 200)
        resp = self.http.post(
            url,
            {
                "category": str(self.category.id),
                "expense_date": "2026-07-02",
                "currency": "USD",
                "amount": "550.00",
                "description": "Office rent updated",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.amount, Decimal("550.00"))
        self.assertEqual(self.expense.amount_usd, Decimal("550.00"))
        self.assertEqual(self.expense.status, OperatingExpense.Status.POSTED)

    def test_posted_expense_can_be_deleted_from_app(self):
        url = reverse("expenses:expense_delete", args=[self.expense.id])
        resp = self.http.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(OperatingExpense.objects.filter(pk=self.expense.id).exists())

    def test_list_shows_edit_and_delete_for_posted(self):
        resp = self.http.get(reverse("expenses:expense_list") + "?date_from=2026-01-01&date_to=2026-12-31")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Edit", content)
        self.assertIn("Delete", content)
        self.assertIn(str(self.expense.id), content)
