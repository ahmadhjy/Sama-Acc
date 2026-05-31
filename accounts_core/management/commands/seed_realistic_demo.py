"""
Seed realistic demo data for a Beirut travel agency (reporting, dashboards, SOA).

Usage:
  python manage.py seed_realistic_demo
  python manage.py seed_realistic_demo --clear   # remove prior seed from this command
"""
from datetime import date, timedelta
from decimal import Decimal
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts_core.models import Client, Currency, Employee, Supplier
from catalog.models import Destination, ServiceType
from expenses.models import OperatingExpense
from purchases.models import ExpenseCategory
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import ARAllocation, MoneyAccount, Payment

SEED_CLIENT_PREFIX = "C-DEMO24-"
SEED_SUPPLIER_PREFIX = "S-DEMO24-"
SEED_PAYMENT_PREFIX = "TMP-SEED-PAY-"
SEED_OPEX_PREFIX = "TMP-SEED-OPEX-"


class Command(BaseCommand):
    help = "Seed realistic travel-agency demo data for reporting and dashboards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove data created by a previous run of this command.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear_seed()
            self.stdout.write(self.style.WARNING("Cleared previous realistic demo data."))

        with transaction.atomic():
            admin = self._ensure_admin()
            rng = random.Random(2024)
            ctx = self._build_master_data(admin, rng)
            invoices = self._create_invoices(admin, ctx, rng)
            self._create_operating_expenses(admin, ctx, rng)
            self._create_payments(admin, ctx, invoices, rng)

        self.stdout.write(
            self.style.SUCCESS(
                "Realistic demo data loaded. "
                f"{len(invoices)} posted invoices, "
                f"{Client.objects.filter(client_code__startswith=SEED_CLIENT_PREFIX).count()} clients, "
                f"{Supplier.objects.filter(supplier_code__startswith=SEED_SUPPLIER_PREFIX).count()} suppliers. "
                "Login: admin / admin12345"
            )
        )

    def _clear_seed(self):
        from purchases.models import SupplierBill
        from treasury.models import APAllocation

        inv_qs = SalesInvoice.objects.filter(client__client_code__startswith=SEED_CLIENT_PREFIX)
        inv_ids = list(inv_qs.values_list("pk", flat=True))

        ARAllocation.objects.filter(sales_invoice_id__in=inv_ids).delete()
        ARAllocation.objects.filter(payment__receipt_no__startswith=SEED_PAYMENT_PREFIX).delete()
        APAllocation.objects.filter(payment__receipt_no__startswith=SEED_PAYMENT_PREFIX).delete()
        Payment.objects.filter(receipt_no__startswith=SEED_PAYMENT_PREFIX).delete()
        OperatingExpense.objects.filter(expense_no__startswith=SEED_OPEX_PREFIX).delete()
        SupplierBill.objects.filter(lines__sales_invoice_line__invoice_id__in=inv_ids).delete()
        inv_qs.delete()

        Client.objects.filter(client_code__startswith=SEED_CLIENT_PREFIX).delete()
        Supplier.objects.filter(supplier_code__startswith=SEED_SUPPLIER_PREFIX).delete()
        Destination.objects.filter(name__in=[d[0] for d in _DESTINATIONS]).delete()

    def _ensure_admin(self):
        user_model = get_user_model()
        admin, _ = user_model.objects.get_or_create(username="admin")
        if not admin.has_usable_password():
            admin.set_password("admin12345")
            admin.is_staff = True
            admin.is_superuser = True
            admin.save()
        return admin

    def _build_master_data(self, admin, rng):
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_active": True, "sort_order": 0})
        Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "is_active": True, "sort_order": 1})

        accountant = Employee.objects.filter(user=admin).first()
        if not accountant:
            accountant = Employee.objects.filter(role=Employee.EmployeeRole.ACCOUNTING).first()
        if not accountant:
            accountant = Employee.objects.create(
                name="Nadine Haddad",
                role=Employee.EmployeeRole.ACCOUNTING,
                user=admin,
                is_active=True,
            )

        sales_team = []
        for name in ("Rami Saleh", "Layla Nassar", "Karim Azar"):
            emp, _ = Employee.objects.get_or_create(
                name=name,
                defaults={"role": Employee.EmployeeRole.SALES, "is_active": True},
            )
            sales_team.append(emp)

        cash_usd, _ = MoneyAccount.objects.get_or_create(
            name="Main cash — USD",
            defaults={"type": MoneyAccount.AccountType.CASH, "currency": "USD", "is_active": True},
        )
        bank_usd, _ = MoneyAccount.objects.get_or_create(
            name="BLOM — USD current",
            defaults={"type": MoneyAccount.AccountType.BANK, "currency": "USD", "is_active": True},
        )
        MoneyAccount.objects.get_or_create(
            name="Whish — USD",
            defaults={"type": MoneyAccount.AccountType.BANK, "currency": "USD", "is_active": True},
        )

        clients = []
        for i, row in enumerate(_CLIENTS, start=1):
            code = f"{SEED_CLIENT_PREFIX}{i:02d}"
            c, created = Client.objects.get_or_create(
                client_code=code,
                defaults={
                    "name_en": row["name"],
                    "type": row["type"],
                    "email": row.get("email", ""),
                    "whatsapp": row.get("phone", ""),
                    "address": row.get("address", ""),
                },
            )
            if not created:
                Client.objects.filter(pk=c.pk).update(
                    name_en=row["name"],
                    type=row["type"],
                    email=row.get("email", ""),
                    whatsapp=row.get("phone", ""),
                )
            clients.append(c)

        suppliers = {}
        for code_suffix, row in _SUPPLIERS.items():
            code = f"{SEED_SUPPLIER_PREFIX}{code_suffix}"
            s, _ = Supplier.objects.get_or_create(
                supplier_code=code,
                defaults={
                    "name": row["name"],
                    "type": row["type"],
                    "email": row.get("email", ""),
                    "default_currency": "USD",
                    "is_active": True,
                },
            )
            suppliers[code_suffix] = s

        destinations = {}
        for i, (name, country) in enumerate(_DESTINATIONS):
            d, _ = Destination.objects.get_or_create(
                name=name,
                defaults={"country": country, "sort_order": i, "is_active": True},
            )
            destinations[name] = d

        service_types = {}
        for code, name in _SERVICE_TYPES:
            st, _ = ServiceType.objects.get_or_create(
                code=code,
                defaults={"name": name, "requires_supplier": True, "default_currency": "USD", "is_active": True},
            )
            service_types[code] = st

        categories = {}
        for code, name in _EXPENSE_CATEGORIES:
            cat, _ = ExpenseCategory.objects.get_or_create(code=code, defaults={"name": name, "is_active": True})
            categories[code] = cat

        return {
            "admin": admin,
            "accountant": accountant,
            "sales_team": sales_team,
            "cash_usd": cash_usd,
            "bank_usd": bank_usd,
            "clients": clients,
            "suppliers": suppliers,
            "destinations": destinations,
            "service_types": service_types,
            "categories": categories,
            "rng": rng,
        }

    def _create_invoices(self, admin, ctx, rng):
        today = date.today()
        invoices = []
        if SalesInvoice.objects.filter(invoice_no__startswith="TMP-SEED-INV-").exists():
            self.stdout.write(self.style.WARNING("Seed invoices already exist — skip (use --clear to reload)."))
            return [
                {"invoice": inv, "pay_plan": "full", "days_ago": 0}
                for inv in SalesInvoice.objects.filter(
                    client__client_code__startswith=SEED_CLIENT_PREFIX,
                    status=SalesInvoice.Status.POSTED,
                ).select_related("client")
            ]

        for spec in _INVOICE_SPECS:
            client = ctx["clients"][spec["client_idx"]]
            sales_emp = ctx["sales_team"][spec["sales_idx"] % len(ctx["sales_team"])]
            issue = today - timedelta(days=spec["days_ago"])
            due = issue + timedelta(days=spec.get("due_days", 14))

            inv = SalesInvoice.objects.create(
                invoice_no=f"TMP-SEED-INV-{len(invoices)+1:04d}",
                client=client,
                sales_employee=sales_emp,
                package_type=spec.get("package", SalesInvoice.PackageType.TICKET),
                issue_date=issue,
                due_date=due,
                currency=spec.get("currency", "USD"),
                exchange_rate_to_usd=Decimal("1.08") if spec.get("currency") == "EUR" else None,
                status=SalesInvoice.Status.DRAFT,
            )

            for line_spec in spec["lines"]:
                st = ctx["service_types"][line_spec["stype"]]
                sup = ctx["suppliers"][line_spec["supplier"]]
                dest = ctx["destinations"].get(line_spec.get("dest"))
                svc_date = issue + timedelta(days=line_spec.get("svc_offset", 0))
                qty = Decimal(str(line_spec.get("qty", 1)))
                sell = Decimal(str(line_spec["sell"]))
                cost = Decimal(str(line_spec["cost"]))

                SalesInvoiceLine.objects.create(
                    invoice=inv,
                    service_type=st,
                    supplier=sup,
                    line_employee=sales_emp,
                    destination=dest,
                    service_date=svc_date,
                    line_data=line_spec.get("data", {}),
                    qty=qty,
                    sell_price=sell,
                    cost_price=cost,
                    notes=line_spec.get("notes", ""),
                )

            inv.recalc_totals_from_lines()
            inv.recalc_usd_amounts()
            inv.post(admin)
            inv.refresh_from_db()
            invoices.append({"invoice": inv, "pay_plan": spec.get("pay_plan", "full"), "days_ago": spec["days_ago"]})

        return invoices

    def _create_operating_expenses(self, admin, ctx, rng):
        today = date.today()
        specs = [
            (0, "RENT", "Hazmieh office rent — March", "1850.00"),
            (32, "RENT", "Hazmieh office rent — February", "1850.00"),
            (63, "RENT", "Hazmieh office rent — January", "1850.00"),
            (5, "SAL", "February salaries — sales & admin", "4200.00"),
            (35, "SAL", "January salaries — sales & admin", "4200.00"),
            (8, "INT", "Ogero business fibre", "95.00"),
            (38, "INT", "Ogero business fibre", "95.00"),
            (12, "MKT", "Instagram ads — Gulf packages", "350.00"),
            (45, "MKT", "Google Ads — Europe summer", "280.00"),
            (18, "OFF", "Stationery & printing", "120.00"),
            (22, "TEL", "Mobile lines — team", "165.00"),
            (52, "TEL", "Mobile lines — team", "165.00"),
            (75, "OFF", "AC maintenance contract", "200.00"),
            (90, "MKT", "Flyer distribution — Achrafieh", "150.00"),
        ]
        for i, (days_ago, cat_code, desc, amount) in enumerate(specs):
            exp = OperatingExpense.objects.create(
                expense_no=f"{SEED_OPEX_PREFIX}{i+1:03d}",
                category=ctx["categories"][cat_code],
                expense_date=today - timedelta(days=days_ago),
                currency="USD",
                amount=Decimal(amount),
                description=desc,
                status=OperatingExpense.Status.DRAFT,
            )
            exp.post(admin)

    def _create_payments(self, admin, ctx, invoice_rows, rng):
        today = date.today()
        pay_n = 0
        cash = ctx["cash_usd"]
        bank = ctx["bank_usd"]

        for row in invoice_rows:
            inv = row["invoice"]
            plan = row["pay_plan"]
            if plan == "none":
                continue

            inv.refresh_from_db()
            total = inv.grand_total
            if plan == "full":
                amt = total
            elif plan == "partial":
                amt = (total * Decimal("0.55")).quantize(Decimal("0.01"))
            elif plan == "overpay":
                amt = (total * Decimal("1.15")).quantize(Decimal("0.01"))
            else:
                amt = total

            pay_currency = "USD"
            if inv.currency != "USD":
                amt = (inv.grand_total_usd * (amt / total if total else Decimal("1"))).quantize(Decimal("0.01"))

            pay_date = inv.issue_date + timedelta(days=rng.randint(2, 12))
            if pay_date > today:
                pay_date = today - timedelta(days=1)

            pay_n += 1
            account = bank if pay_n % 3 == 0 else cash
            p = Payment.objects.create(
                receipt_no=f"{SEED_PAYMENT_PREFIX}{pay_n:04d}",
                direction=Payment.Direction.IN,
                party_type=Payment.PartyType.CLIENT,
                client=inv.client,
                money_account=account,
                date=pay_date,
                currency=pay_currency,
                amount=amt,
                reference=f"Bank transfer ref {rng.randint(100000, 999999)}",
                note=f"Payment toward {inv.invoice_no}",
                status=Payment.Status.DRAFT,
            )
            p.post(admin)
            if plan in ("full", "partial", "overpay") and amt > 0:
                alloc = min(amt, inv.grand_total) if plan != "overpay" else inv.grand_total
                ARAllocation.objects.get_or_create(
                    payment=p,
                    sales_invoice=inv,
                    defaults={"allocated_amount": alloc},
                )

        # Supplier settlements (partial) for recent months
        from purchases.models import SupplierBill

        bills = list(
            SupplierBill.objects.filter(
                supplier__supplier_code__startswith=SEED_SUPPLIER_PREFIX,
                status=SupplierBill.Status.POSTED,
            ).order_by("bill_date")
        )
        for bill in bills[::2]:
            if rng.random() < 0.35:
                continue
            pay_n += 1
            amt = (bill.grand_total * Decimal(rng.choice(["0.5", "0.7", "1.0"]))).quantize(Decimal("0.01"))
            if amt <= 0:
                continue
            p = Payment.objects.create(
                receipt_no=f"{SEED_PAYMENT_PREFIX}{pay_n:04d}",
                direction=Payment.Direction.OUT,
                party_type=Payment.PartyType.SUPPLIER,
                supplier=bill.supplier,
                money_account=bank,
                date=min(bill.bill_date + timedelta(days=rng.randint(5, 20)), today),
                currency="USD",
                amount=amt,
                reference=f"Supplier settlement {bill.bill_no}",
                status=Payment.Status.DRAFT,
            )
            p.post(admin)
            from treasury.models import APAllocation

            already = sum((a.allocated_amount for a in bill.allocations.all()), Decimal("0.00"))
            remaining = bill.grand_total - already
            alloc_amt = min(amt, remaining)
            if alloc_amt <= 0:
                continue
            APAllocation.objects.create(
                payment=p,
                supplier_bill=bill,
                allocated_amount=alloc_amt,
            )


# ---------------------------------------------------------------------------
# Static datasets — real-sounding names (Lebanon / regional travel trade)
# ---------------------------------------------------------------------------

_CLIENTS = [
    {
        "name": "Khoury & Partners sal",
        "type": Client.ClientType.CORPORATE,
        "email": "travel@khourypartners.lb",
        "phone": "+961 1 234 567",
        "address": "Ashrafieh, Beirut",
    },
    {
        "name": "Nadia Mansour",
        "type": Client.ClientType.INDIVIDUAL,
        "email": "nadia.mansour@gmail.com",
        "phone": "+961 3 456 789",
        "address": "Jounieh",
    },
    {
        "name": "Mika Hospitality Group",
        "type": Client.ClientType.CORPORATE,
        "email": "reservations@mikahotels.com",
        "phone": "+961 1 510 200",
        "address": "Dbayeh Highway",
    },
    {
        "name": "Gulf Petroleum Services",
        "type": Client.ClientType.CORPORATE,
        "email": "mobility@gulfpetro.ae",
        "phone": "+971 4 555 0101",
        "address": "Dubai, UAE",
    },
    {
        "name": "Fadi & Rana Gemayel",
        "type": Client.ClientType.INDIVIDUAL,
        "email": "fadi.gemayel@outlook.com",
        "phone": "+961 70 112 233",
        "address": "Byblos",
    },
    {
        "name": "Beirut Medical Center",
        "type": Client.ClientType.CORPORATE,
        "email": "hr@bmc.org.lb",
        "phone": "+961 1 604 000",
        "address": "Hazmieh",
    },
    {
        "name": "Cedar Education Institute",
        "type": Client.ClientType.CORPORATE,
        "email": "intl@cedaredu.lb",
        "phone": "+961 5 955 400",
        "address": "Hamra, Beirut",
    },
    {
        "name": "Royal Palace Events",
        "type": Client.ClientType.CORPORATE,
        "email": "events@royalpalace.lb",
        "phone": "+961 1 333 900",
        "address": "Sin el Fil",
    },
    {
        "name": "Elie & Sonia Daher",
        "type": Client.ClientType.INDIVIDUAL,
        "email": "sonia.daher@yahoo.com",
        "phone": "+961 76 888 120",
        "address": "Zalka",
    },
    {
        "name": "Phoenicia Trading Co.",
        "type": Client.ClientType.CORPORATE,
        "email": "logistics@phoeniciatrade.lb",
        "phone": "+961 1 842 100",
        "address": "Khalde",
    },
    {
        "name": "Sara Abou Jaoude",
        "type": Client.ClientType.INDIVIDUAL,
        "email": "sara.abj@hotmail.com",
        "phone": "+961 3 900 445",
        "address": "Batroun",
    },
    {
        "name": "Horizon NGO",
        "type": Client.ClientType.CORPORATE,
        "email": "programs@horizonngo.org",
        "phone": "+961 1 750 330",
        "address": "Badaro, Beirut",
    },
]

_SUPPLIERS = {
    "MEA": {"name": "Middle East Airlines", "type": Supplier.SupplierType.AIRLINE, "email": "agency@mea.com.lb"},
    "EMI": {"name": "Emirates Holidays", "type": Supplier.SupplierType.DMC, "email": "bey.sales@emirates.com"},
    "HIL": {"name": "Hilton Beirut Habtoor", "type": Supplier.SupplierType.HOTEL, "email": "reservations@hiltonlb.com"},
    "VFS": {"name": "VFS Global — Schengen", "type": Supplier.SupplierType.VISA, "email": "leb@vfsglobal.com"},
    "COV": {"name": "Cover-More Assistance", "type": Supplier.SupplierType.INSURANCE, "email": "claims@covermore.com"},
    "RWT": {"name": "Royal Wings Transport", "type": Supplier.SupplierType.TRANSFER, "email": "ops@royalwings.lb"},
    "LDT": {"name": "Lebanon DMC Tours", "type": Supplier.SupplierType.DMC, "email": "groups@ldmc.lb"},
    "TKT": {"name": "Turkish Airlines Agency", "type": Supplier.SupplierType.AIRLINE, "email": "bey@thy.com"},
    "MAR": {"name": "Mövenpick Beirut", "type": Supplier.SupplierType.HOTEL, "email": "sales@movenpick.com"},
    "QTR": {"name": "Qatar Airways — BEY", "type": Supplier.SupplierType.AIRLINE, "email": "beyoffice@qatarairways.com"},
}

_DESTINATIONS = [
    ("Dubai", "UAE"),
    ("Paris", "France"),
    ("Istanbul", "Turkey"),
    ("Rome", "Italy"),
    ("Cairo", "Egypt"),
    ("London", "United Kingdom"),
    ("Athens", "Greece"),
    ("Riyadh", "Saudi Arabia"),
    ("Barcelona", "Spain"),
    ("Geneva", "Switzerland"),
    ("Amman", "Jordan"),
    ("Frankfurt", "Germany"),
]

_SERVICE_TYPES = [
    ("FLT", "Flight ticket"),
    ("HTL", "Hotel booking"),
    ("VIS", "Visa service"),
    ("INS", "Travel insurance"),
    ("TRF", "Airport transfer"),
    ("TOR", "Tour package"),
]

_EXPENSE_CATEGORIES = [
    ("RENT", "Office rent"),
    ("SAL", "Salaries"),
    ("INT", "Internet & telecom"),
    ("MKT", "Marketing"),
    ("OFF", "Office supplies"),
    ("TEL", "Telephone"),
]

# client_idx, sales_idx, days_ago, package, lines[], pay_plan: full|partial|none|overpay
_INVOICE_SPECS = [
    {
        "client_idx": 0,
        "sales_idx": 0,
        "days_ago": 12,
        "package": "TICKET",
        "pay_plan": "partial",
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "Dubai", "sell": "1240", "cost": "980", "data": {"pnr": "ME7K2P", "passenger": "J. Khoury"}},
            {"stype": "TRF", "supplier": "RWT", "dest": "Dubai", "sell": "85", "cost": "55"},
        ],
    },
    {
        "client_idx": 1,
        "sales_idx": 1,
        "days_ago": 8,
        "package": "HOTEL",
        "pay_plan": "full",
        "lines": [
            {"stype": "HTL", "supplier": "HIL", "dest": "Paris", "sell": "890", "cost": "720", "data": {"nights": "4", "guest": "N. Mansour"}},
        ],
    },
    {
        "client_idx": 2,
        "sales_idx": 0,
        "days_ago": 25,
        "package": "TICKET",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "TKT", "dest": "Istanbul", "sell": "620", "cost": "490", "qty": "2"},
            {"stype": "HTL", "supplier": "MAR", "dest": "Istanbul", "sell": "1100", "cost": "890"},
        ],
    },
    {
        "client_idx": 3,
        "sales_idx": 2,
        "days_ago": 45,
        "package": "TICKET",
        "pay_plan": "partial",
        "lines": [
            {"stype": "FLT", "supplier": "QTR", "dest": "Riyadh", "sell": "2100", "cost": "1750", "qty": "3"},
            {"stype": "TRF", "supplier": "RWT", "dest": "Riyadh", "sell": "240", "cost": "180", "qty": "3"},
        ],
    },
    {
        "client_idx": 4,
        "sales_idx": 1,
        "days_ago": 5,
        "package": "VISA",
        "pay_plan": "full",
        "lines": [
            {"stype": "VIS", "supplier": "VFS", "dest": "Paris", "sell": "195", "cost": "120", "data": {"applicant": "F. Gemayel"}},
            {"stype": "INS", "supplier": "COV", "dest": "Paris", "sell": "78", "cost": "45"},
        ],
    },
    {
        "client_idx": 5,
        "sales_idx": 0,
        "days_ago": 60,
        "package": "TICKET",
        "pay_plan": "none",
        "due_days": 30,
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "London", "sell": "1580", "cost": "1290", "qty": "2"},
        ],
    },
    {
        "client_idx": 6,
        "sales_idx": 2,
        "days_ago": 38,
        "package": "TOUR",
        "pay_plan": "partial",
        "lines": [
            {"stype": "TOR", "supplier": "LDT", "dest": "Athens", "sell": "2400", "cost": "1950", "data": {"group": "Student exchange — 12 pax"}},
            {"stype": "INS", "supplier": "COV", "dest": "Athens", "sell": "360", "cost": "220"},
        ],
    },
    {
        "client_idx": 7,
        "sales_idx": 1,
        "days_ago": 72,
        "package": "HOTEL",
        "pay_plan": "none",
        "due_days": 45,
        "lines": [
            {"stype": "HTL", "supplier": "MAR", "dest": "Barcelona", "sell": "3200", "cost": "2650"},
            {"stype": "TRF", "supplier": "RWT", "dest": "Barcelona", "sell": "420", "cost": "310"},
        ],
    },
    {
        "client_idx": 8,
        "sales_idx": 0,
        "days_ago": 18,
        "package": "TICKET",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "EMI", "dest": "Dubai", "sell": "980", "cost": "810"},
        ],
    },
    {
        "client_idx": 9,
        "sales_idx": 2,
        "days_ago": 95,
        "package": "TRANSFER",
        "pay_plan": "partial",
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "Frankfurt", "sell": "1320", "cost": "1080"},
            {"stype": "FLT", "supplier": "TKT", "dest": "Frankfurt", "sell": "1280", "cost": "1040"},
        ],
    },
    {
        "client_idx": 10,
        "sales_idx": 1,
        "days_ago": 3,
        "package": "INSURANCE",
        "pay_plan": "overpay",
        "lines": [
            {"stype": "INS", "supplier": "COV", "dest": "Geneva", "sell": "145", "cost": "90"},
            {"stype": "FLT", "supplier": "MEA", "dest": "Geneva", "sell": "1120", "cost": "920"},
        ],
    },
    {
        "client_idx": 11,
        "sales_idx": 0,
        "days_ago": 110,
        "package": "TICKET",
        "pay_plan": "none",
        "due_days": 60,
        "lines": [
            {"stype": "FLT", "supplier": "QTR", "dest": "Amman", "sell": "890", "cost": "710", "qty": "4"},
        ],
    },
    {
        "client_idx": 0,
        "sales_idx": 1,
        "days_ago": 55,
        "package": "HOTEL",
        "pay_plan": "full",
        "lines": [
            {"stype": "HTL", "supplier": "HIL", "dest": "Cairo", "sell": "760", "cost": "610"},
        ],
    },
    {
        "client_idx": 3,
        "sales_idx": 0,
        "days_ago": 28,
        "package": "TICKET",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "Dubai", "sell": "540", "cost": "430"},
        ],
    },
    {
        "client_idx": 5,
        "sales_idx": 2,
        "days_ago": 140,
        "package": "VISA",
        "pay_plan": "partial",
        "lines": [
            {"stype": "VIS", "supplier": "VFS", "dest": "London", "sell": "420", "cost": "280", "qty": "3"},
        ],
    },
    {
        "client_idx": 2,
        "sales_idx": 1,
        "days_ago": 85,
        "package": "TOUR",
        "pay_plan": "none",
        "due_days": 30,
        "lines": [
            {"stype": "TOR", "supplier": "LDT", "dest": "Rome", "sell": "1850", "cost": "1520"},
            {"stype": "HTL", "supplier": "MAR", "dest": "Rome", "sell": "980", "cost": "800"},
        ],
    },
    {
        "client_idx": 7,
        "sales_idx": 0,
        "days_ago": 22,
        "package": "TICKET",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "TKT", "dest": "Istanbul", "sell": "720", "cost": "580"},
            {"stype": "TRF", "supplier": "RWT", "dest": "Istanbul", "sell": "95", "cost": "60"},
        ],
    },
    {
        "client_idx": 4,
        "sales_idx": 2,
        "days_ago": 48,
        "package": "HOTEL",
        "pay_plan": "partial",
        "lines": [
            {"stype": "HTL", "supplier": "HIL", "dest": "Athens", "sell": "1340", "cost": "1090"},
        ],
    },
    {
        "client_idx": 9,
        "sales_idx": 1,
        "days_ago": 15,
        "package": "TICKET",
        "currency": "EUR",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "EMI", "dest": "Paris", "sell": "680", "cost": "540"},
            {"stype": "HTL", "supplier": "MAR", "dest": "Paris", "sell": "920", "cost": "750"},
        ],
    },
    {
        "client_idx": 1,
        "sales_idx": 0,
        "days_ago": 165,
        "package": "TICKET",
        "pay_plan": "none",
        "due_days": 90,
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "Cairo", "sell": "450", "cost": "360"},
        ],
    },
    {
        "client_idx": 6,
        "sales_idx": 1,
        "days_ago": 33,
        "package": "SECURITY",
        "pay_plan": "full",
        "lines": [
            {"stype": "VIS", "supplier": "VFS", "dest": "London", "sell": "280", "cost": "180", "qty": "2"},
            {"stype": "FLT", "supplier": "QTR", "dest": "London", "sell": "1680", "cost": "1380", "qty": "2"},
        ],
    },
    {
        "client_idx": 8,
        "sales_idx": 2,
        "days_ago": 200,
        "package": "TICKET",
        "pay_plan": "partial",
        "lines": [
            {"stype": "FLT", "supplier": "MEA", "dest": "Barcelona", "sell": "990", "cost": "800"},
            {"stype": "INS", "supplier": "COV", "dest": "Barcelona", "sell": "120", "cost": "75"},
        ],
    },
    {
        "client_idx": 10,
        "sales_idx": 0,
        "days_ago": 42,
        "package": "HOTEL",
        "pay_plan": "full",
        "lines": [
            {"stype": "HTL", "supplier": "HIL", "dest": "Dubai", "sell": "1450", "cost": "1180"},
            {"stype": "TRF", "supplier": "RWT", "dest": "Dubai", "sell": "110", "cost": "70"},
        ],
    },
    {
        "client_idx": 11,
        "sales_idx": 1,
        "days_ago": 68,
        "package": "TOUR",
        "pay_plan": "partial",
        "lines": [
            {"stype": "TOR", "supplier": "LDT", "dest": "Amman", "sell": "3200", "cost": "2700"},
        ],
    },
    {
        "client_idx": 0,
        "sales_idx": 2,
        "days_ago": 175,
        "package": "TICKET",
        "pay_plan": "none",
        "due_days": 120,
        "lines": [
            {"stype": "FLT", "supplier": "TKT", "dest": "Frankfurt", "sell": "780", "cost": "640"},
        ],
    },
    {
        "client_idx": 3,
        "sales_idx": 1,
        "days_ago": 7,
        "package": "TICKET",
        "pay_plan": "full",
        "lines": [
            {"stype": "FLT", "supplier": "QTR", "dest": "Riyadh", "sell": "890", "cost": "720"},
        ],
    },
]
