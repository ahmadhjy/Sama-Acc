from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts_core.models import Client, Currency, Employee, Supplier
from catalog.models import ServiceInstance, ServiceType
from purchases.models import ExpenseCategory, SupplierBill, SupplierBillLine
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import APAllocation, ARAllocation, MoneyAccount, Payment


class Command(BaseCommand):
    help = "Seed demo data for local testing."

    def handle(self, *args, **options):
        user_model = get_user_model()
        admin, _ = user_model.objects.get_or_create(username="admin")
        if not admin.has_usable_password():
            admin.set_password("admin12345")
            admin.is_staff = True
            admin.is_superuser = True
            admin.save()

        Currency.objects.get_or_create(
            code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0}
        )

        employee, _ = Employee.objects.get_or_create(name="Main Accountant", defaults={"role": Employee.EmployeeRole.ADMIN, "user": admin})
        if employee.user_id is None:
            employee.user = admin
            employee.save(update_fields=["user"])

        client, _ = Client.objects.get_or_create(client_code="C-0001", defaults={"name_en": "Demo Travel Client"})
        supplier, _ = Supplier.objects.get_or_create(supplier_code="S-0001", defaults={"name": "Demo Airline Supplier"})
        landlord, _ = Supplier.objects.get_or_create(supplier_code="S-RENT", defaults={"name": "Office Landlord"})
        isp, _ = Supplier.objects.get_or_create(supplier_code="S-ISP", defaults={"name": "Internet Provider"})
        payroll, _ = Supplier.objects.get_or_create(supplier_code="S-PAY", defaults={"name": "Payroll Provider"})

        rent_cat, _ = ExpenseCategory.objects.get_or_create(code="RENT", defaults={"name": "Office Rent"})
        internet_cat, _ = ExpenseCategory.objects.get_or_create(code="INT", defaults={"name": "Internet"})
        salary_cat, _ = ExpenseCategory.objects.get_or_create(code="SAL", defaults={"name": "Salaries"})

        service_type, _ = ServiceType.objects.get_or_create(name="Flight Ticket", code="TKT")
        service_instance, _ = ServiceInstance.objects.get_or_create(service_type=service_type, data={"pnr": "PNR001", "ticket_no": "ETK001"})

        cash_usd, _ = MoneyAccount.objects.get_or_create(name="Cashbox USD", defaults={"type": MoneyAccount.AccountType.CASH, "currency": "USD"})
        MoneyAccount.objects.get_or_create(name="Bank USD", defaults={"type": MoneyAccount.AccountType.BANK, "currency": "USD"})

        invoice, created = SalesInvoice.objects.get_or_create(
            invoice_no="TMP-DEMO-INV",
            defaults={
                "client": client,
                "sales_employee": employee,
                "issue_date": date.today(),
                "due_date": date.today() + timedelta(days=15),
                "currency": "USD",
            },
        )
        if created:
            ticket_data = dict(service_instance.data) if service_instance.data else {}
            SalesInvoiceLine.objects.create(
                invoice=invoice,
                service_type=service_type,
                supplier=supplier,
                service_instance=service_instance,
                line_data=ticket_data,
                line_employee=employee,
                qty=1,
                sell_price=Decimal("600"),
                cost_price=Decimal("450"),
            )
            invoice.recalc_totals_from_lines()
            invoice.refresh_from_db()
            invoice.recalc_usd_amounts()
            invoice.post(admin)

        bill, created = SupplierBill.objects.get_or_create(
            bill_no="TMP-DEMO-BILL",
            defaults={
                "supplier": supplier,
                "bill_date": date.today(),
                "due_date": date.today() + timedelta(days=30),
                "currency": "USD",
            },
        )
        if created:
            SupplierBillLine.objects.create(
                bill=bill,
                line_kind=SupplierBillLine.LineKind.SERVICE,
                service_instance=service_instance,
                description="Airline charge",
                cost_amount=Decimal("450"),
            )
            bill.post(admin)

        opex_bill, created = SupplierBill.objects.get_or_create(
            bill_no="TMP-DEMO-OPEX",
            defaults={
                "supplier": landlord,
                "bill_date": date.today(),
                "due_date": date.today() + timedelta(days=10),
                "currency": "USD",
            },
        )
        if created:
            SupplierBillLine.objects.create(
                bill=opex_bill,
                line_kind=SupplierBillLine.LineKind.OPEX,
                expense_category=rent_cat,
                description="Office rent",
                cost_amount=Decimal("300"),
            )
            SupplierBillLine.objects.create(
                bill=opex_bill,
                line_kind=SupplierBillLine.LineKind.OPEX,
                expense_category=internet_cat,
                description="Internet bill",
                cost_amount=Decimal("60"),
            )
            SupplierBillLine.objects.create(
                bill=opex_bill,
                line_kind=SupplierBillLine.LineKind.OPEX,
                expense_category=salary_cat,
                description="Salary expense",
                cost_amount=Decimal("700"),
            )
            opex_bill.post(admin)

        in_payment, created = Payment.objects.get_or_create(
            receipt_no="TMP-DEMO-PIN",
            defaults={
                "direction": Payment.Direction.IN,
                "party_type": Payment.PartyType.CLIENT,
                "client": client,
                "money_account": cash_usd,
                "date": date.today(),
                "currency": "USD",
                "amount": Decimal("600"),
            },
        )
        if created:
            in_payment.post(admin)
        ARAllocation.objects.get_or_create(payment=in_payment, sales_invoice=invoice, defaults={"allocated_amount": Decimal("600")})

        out_payment, created = Payment.objects.get_or_create(
            receipt_no="TMP-DEMO-POUT",
            defaults={
                "direction": Payment.Direction.OUT,
                "party_type": Payment.PartyType.SUPPLIER,
                "supplier": supplier,
                "money_account": cash_usd,
                "date": date.today(),
                "currency": "USD",
                "amount": Decimal("450"),
            },
        )
        if created:
            out_payment.post(admin)
        APAllocation.objects.get_or_create(payment=out_payment, supplier_bill=bill, defaults={"allocated_amount": Decimal("450")})

        opex_payment, created = Payment.objects.get_or_create(
            receipt_no="TMP-DEMO-OPEX-PAY",
            defaults={
                "direction": Payment.Direction.OUT,
                "party_type": Payment.PartyType.SUPPLIER,
                "supplier": landlord,
                "money_account": cash_usd,
                "date": date.today(),
                "currency": "USD",
                "amount": Decimal("1060"),
            },
        )
        if created:
            opex_payment.post(admin)
        APAllocation.objects.get_or_create(payment=opex_payment, supplier_bill=opex_bill, defaults={"allocated_amount": Decimal("1060")})

        self.stdout.write(self.style.SUCCESS("Demo data seeded. Login: admin / admin12345"))
