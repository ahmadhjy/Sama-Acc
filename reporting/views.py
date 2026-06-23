from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from reporting.date_ranges import resolve_report_dates
from accounts_core.export_names import export_filename, export_period_suffix
from accounts_core.models import Client, Employee, Supplier
from accounts_core.pdf_utils import pdf_download_query, render_or_pdf
from reporting.salesman import build_brief_report, build_detailed_report
from reporting.balances import client_ar_balance, supplier_ap_balance, supplier_line_purchases
from reporting.client_statement_rows import build_client_statement_rows
from reporting.payment_amounts import payment_usd_amount
from reporting.statement_refs import payment_ref_url
from reporting.statement_summary import (
    _client_period_movement,
    _split_balance_dr_cr,
    _supplier_period_movement,
    build_client_summary_rows,
    build_supplier_summary_rows,
    profit_summary_row,
    summarize_totals,
    summarize_supplier_totals,
)
from reporting.statement_running import annotate_client_statement_rows, annotate_supplier_statement_rows
from reporting.supplier_statement_rows import build_supplier_statement_rows
from purchases.models import SupplierBill, SupplierBillLine
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, MoneyAccount, Payment, ReconciliationRecord


def _sum_client_payments_usd(payments_qs):
    return sum((payment_usd_amount(p) for p in payments_qs), Decimal("0.00"))


def reports_home(request):
    if request.GET.get("format") != "pdf":
        params = request.GET.copy()
        params["tab"] = "reports"
        qs = params.urlencode()
        return redirect("/?" + qs if qs else "/?tab=reports")

    df, dt, _ = resolve_report_dates(request)

    inv_q = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
    bill_q = SupplierBill.objects.filter(status=SupplierBill.Status.POSTED)
    pay_q = Payment.objects.filter(status=Payment.Status.POSTED)
    cogs_q = SupplierBill.objects.filter(status=SupplierBill.Status.POSTED, lines__line_kind="SERVICE")
    if df:
        inv_q = inv_q.filter(issue_date__gte=df)
        pay_q = pay_q.filter(date__gte=df)
        bill_q = bill_q.filter(bill_date__gte=df)
        cogs_q = cogs_q.filter(bill_date__gte=df)
    if dt:
        inv_q = inv_q.filter(issue_date__lte=dt)
        pay_q = pay_q.filter(date__lte=dt)
        bill_q = bill_q.filter(bill_date__lte=dt)
        cogs_q = cogs_q.filter(bill_date__lte=dt)

    posted_invoices_total = inv_q.aggregate(total=Sum("grand_total_usd")).get("total") or 0
    posted_bills_total = bill_q.aggregate(total=Sum("grand_total")).get("total") or 0
    posted_payments_total = pay_q.aggregate(total=Sum("amount")).get("total") or 0
    posted_cogs_total = cogs_q.aggregate(total=Sum("lines__cost_amount")).get("total") or 0
    from expenses.models import OperatingExpense

    opex_q = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED)
    if df:
        opex_q = opex_q.filter(expense_date__gte=df)
    if dt:
        opex_q = opex_q.filter(expense_date__lte=dt)
    total_opex = opex_q.aggregate(total=Sum("amount_usd")).get("total") or 0
    posted_opex_total = total_opex
    standalone_opex_total = total_opex
    net_profit_estimate = posted_invoices_total - posted_cogs_total - total_opex
    return render_or_pdf(
        request,
        "reporting/reports_home.html",
        {
            "date_from": df,
            "date_to": dt,
            "posted_invoices_total": posted_invoices_total,
            "posted_bills_total": posted_bills_total,
            "posted_payments_total": posted_payments_total,
            "gross_margin_estimate": posted_invoices_total - posted_bills_total,
            "posted_cogs_total": posted_cogs_total,
            "posted_opex_total": posted_opex_total,
            "standalone_opex_total": standalone_opex_total,
            "total_opex": total_opex,
            "net_profit_estimate": net_profit_estimate,
            "pdf_report_title": "Reporting Overview",
            "pdf_report_subtitle": "Summary for posted documents in the selected period",
        },
        export_filename("Reporting_Overview", export_period_suffix(df, dt)),
    )


def _client_rows_raw(client, date_from=None, date_to=None):
    return build_client_statement_rows(client, date_from, date_to)


def client_statement(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    df, dt, _ = resolve_report_dates(request)
    rows = _client_rows_raw(client, df, dt)
    rows, tot_dr, tot_cr, closing_balance = annotate_client_statement_rows(rows)
    return render_or_pdf(
        request,
        "reporting/client_statement.html",
        {
            "client": client,
            "rows": rows,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "closing_balance": closing_balance,
            "date_from": df,
            "date_to": dt,
            "pdf_report_title": "Statement of Account",
            "pdf_report_subtitle": f"{client.name_en} ({client.client_code})",
            "pdf_account_range": f"Client code: {client.client_code}",
            "pdf_account_name": client.name_en,
            "pdf_account_id": client.client_code,
        },
        export_filename("Statement", client.name_en, client.client_code, export_period_suffix(df, dt)),
    )


def all_clients_statement(request):
    df, dt, _ = resolve_report_dates(request)
    q = (request.GET.get("q") or "").strip()
    clients = Client.objects.all().order_by("name_en")
    if q:
        clients = clients.filter(Q(name_en__icontains=q) | Q(client_code__icontains=q))
    rows = build_client_summary_rows(clients, df, dt)
    tot_dr, tot_cr, bal_dr, bal_cr, total_balance = summarize_totals(rows)
    return render_or_pdf(
        request,
        "reporting/all_clients_statement.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "q": q,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "bal_dr": bal_dr,
            "bal_cr": bal_cr,
            "total_balance": total_balance,
            "pdf_report_title": "Statement of Account — All Clients",
            "pdf_report_subtitle": "Summary balance per client for the selected period",
        },
        export_filename("All_Clients_Statement", export_period_suffix(df, dt)),
    )


def ar_aging(request):
    today = date.today()
    df, dt, _ = resolve_report_dates(request)
    data = []
    qs = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses()).select_related("client")
    if df:
        qs = qs.filter(issue_date__gte=df)
    if dt:
        qs = qs.filter(issue_date__lte=dt)
    for invoice in qs:
        allocated = sum([x.allocated_amount for x in invoice.allocations.all()], Decimal("0.00"))
        due = invoice.grand_total - allocated
        if due <= 0:
            continue
        due_date = invoice.due_date or invoice.issue_date
        days = (today - due_date).days
        buckets = {
            "not_due": Decimal("0.00"),
            "b0_30": Decimal("0.00"),
            "b31_60": Decimal("0.00"),
            "b61_90": Decimal("0.00"),
            "b90_plus": Decimal("0.00"),
        }
        if days < 0:
            buckets["not_due"] = due
        elif days <= 30:
            buckets["b0_30"] = due
        elif days <= 60:
            buckets["b31_60"] = due
        elif days <= 90:
            buckets["b61_90"] = due
        else:
            buckets["b90_plus"] = due
        data.append({"invoice": invoice, "due": due, **buckets})
    return render_or_pdf(
        request,
        "reporting/ar_aging.html",
        {
            "rows": data,
            "date_from": df,
            "date_to": dt,
            "pdf_report_title": "Accounts Receivable Aging",
            "pdf_report_subtitle": "Outstanding posted invoices by due-date bucket",
        },
        export_filename("AR_Aging", export_period_suffix(df, dt)),
    )




def _supplier_pdf_subtitle(supplier):
    parts = [supplier.name, f"Code: {supplier.supplier_code}"]
    parts.extend(supplier.contact_lines())
    return " | ".join(parts)


def supplier_statement(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    df, dt, _ = resolve_report_dates(request)
    rows = build_supplier_statement_rows(supplier, df, dt)
    rows, tot_dr, tot_cr, closing_balance = annotate_supplier_statement_rows(rows)
    return render_or_pdf(
        request,
        "reporting/supplier_statement.html",
        {
            "supplier": supplier,
            "rows": rows,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "closing_balance": closing_balance,
            "date_from": df,
            "date_to": dt,
            "pdf_report_title": "Supplier Statement",
            "pdf_report_subtitle": _supplier_pdf_subtitle(supplier),
            "pdf_account_range": f"Supplier code: {supplier.supplier_code}",
            "pdf_account_name": supplier.name,
            "pdf_account_id": supplier.supplier_code,
        },
        export_filename("Supplier_Statement", supplier.name, supplier.supplier_code, export_period_suffix(df, dt)),
    )


def all_suppliers_statement(request):
    df, dt, _ = resolve_report_dates(request)
    q = (request.GET.get("q") or "").strip()
    suppliers = Supplier.objects.all().order_by("name")
    if q:
        suppliers = suppliers.filter(Q(name__icontains=q) | Q(supplier_code__icontains=q))
    rows = build_supplier_summary_rows(suppliers, df, dt)
    tot_dr, tot_cr, bal_dr, bal_cr, total_balance = summarize_supplier_totals(rows)
    return render_or_pdf(
        request,
        "reporting/all_suppliers_statement.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "q": q,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "bal_dr": bal_dr,
            "bal_cr": bal_cr,
            "total_balance": total_balance,
            "pdf_report_title": "Supplier Statement — All Suppliers",
            "pdf_report_subtitle": "Summary balance per supplier (service lines from service date onward)",
        },
        export_filename("All_Suppliers_Statement", export_period_suffix(df, dt)),
    )


def ap_aging(request):
    today = date.today()
    df, dt, _ = resolve_report_dates(request)
    data = []
    qs = SupplierBill.objects.filter(status=SupplierBill.Status.POSTED).select_related("supplier")
    if df:
        qs = qs.filter(bill_date__gte=df)
    if dt:
        qs = qs.filter(bill_date__lte=dt)
    for bill in qs:
        allocated = sum([x.allocated_amount for x in bill.allocations.all()], Decimal("0.00"))
        due = bill.grand_total - allocated
        if due <= 0:
            continue
        due_date = bill.due_date or bill.bill_date
        days = (today - due_date).days
        buckets = {
            "not_due": Decimal("0.00"),
            "b0_30": Decimal("0.00"),
            "b31_60": Decimal("0.00"),
            "b61_90": Decimal("0.00"),
            "b90_plus": Decimal("0.00"),
        }
        if days < 0:
            buckets["not_due"] = due
        elif days <= 30:
            buckets["b0_30"] = due
        elif days <= 60:
            buckets["b31_60"] = due
        elif days <= 90:
            buckets["b61_90"] = due
        else:
            buckets["b90_plus"] = due
        data.append({"bill": bill, "due": due, **buckets})
    return render_or_pdf(
        request,
        "reporting/ap_aging.html",
        {
            "rows": data,
            "date_from": df,
            "date_to": dt,
            "pdf_report_title": "Accounts Payable Aging",
            "pdf_report_subtitle": "Outstanding posted supplier bills by due-date bucket",
        },
        export_filename("AP_Aging", export_period_suffix(df, dt)),
    )


def cash_movement(request):
    rows = []
    for account in MoneyAccount.objects.filter(is_active=True).order_by("name"):
        expected = ReconciliationRecord.compute_expected_balance(account, date.today())
        rows.append({"account": account, "expected_closing": expected})
    return render_or_pdf(
        request,
        "reporting/cash_movement.html",
        {
            "rows": rows,
            "pdf_report_title": "Cash Movement",
            "pdf_report_subtitle": "Expected balance per money account (as of today)",
        },
        export_filename("Cash_Movement"),
    )


def opex_by_category(request):
    from expenses.models import OperatingExpense

    df, dt, _ = resolve_report_dates(request)
    qs = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED)
    if df:
        qs = qs.filter(expense_date__gte=df)
    if dt:
        qs = qs.filter(expense_date__lte=dt)
    rows = (
        qs.values("category__code", "category__name")
        .annotate(total=Sum("amount_usd"))
        .order_by("category__code")
    )
    # Normalize keys for template / PDF preset
    rows = [
        {
            "expense_category__code": r.get("category__code") or "UNCAT",
            "expense_category__name": r.get("category__name") or "Uncategorized",
            "total": r.get("total") or Decimal("0.00"),
        }
        for r in rows
    ]
    return render_or_pdf(
        request,
        "reporting/opex_by_category.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "pdf_report_title": "Operating Expenses by Category",
            "pdf_report_subtitle": "Posted operating expenses from the Operating Expenses module (USD)",
        },
        export_filename("Operating_Expenses_by_Category", export_period_suffix(df, dt)),
    )


def activity_trial_balance(request):
    """P&L-style trial listing from posted sales, COGS service lines, and OPEX lines."""
    df, dt, period_label = resolve_report_dates(request)

    inv = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
    if df:
        inv = inv.filter(issue_date__gte=df)
    if dt:
        inv = inv.filter(issue_date__lte=dt)
    sales_total = inv.aggregate(t=Sum("grand_total_usd"))["t"] or Decimal("0.00")
    currency = inv.exclude(currency="").values_list("currency", flat=True).first() or "USD"

    cogs_lines = SupplierBillLine.objects.filter(
        line_kind=SupplierBillLine.LineKind.SERVICE,
        bill__status=SupplierBill.Status.POSTED,
    )
    if df:
        cogs_lines = cogs_lines.filter(bill__bill_date__gte=df)
    if dt:
        cogs_lines = cogs_lines.filter(bill__bill_date__lte=dt)
    cogs_total = cogs_lines.aggregate(t=Sum("cost_amount"))["t"] or Decimal("0.00")

    rows = [
        {
            "account": "4010000001",
            "name": "Sales Revenue",
            "curr": currency,
            "tot_dr": Decimal("0.00"),
            "tot_cr": sales_total,
            "bal_dr": Decimal("0.00"),
            "bal_cr": sales_total,
        },
        {
            "account": "5010000001",
            "name": "Cost of Sales (service supplier bills)",
            "curr": currency,
            "tot_dr": cogs_total,
            "tot_cr": Decimal("0.00"),
            "bal_dr": cogs_total,
            "bal_cr": Decimal("0.00"),
        },
    ]

    from expenses.models import OperatingExpense

    standalone_qs = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED).select_related("category")
    if df:
        standalone_qs = standalone_qs.filter(expense_date__gte=df)
    if dt:
        standalone_qs = standalone_qs.filter(expense_date__lte=dt)
    for exp in standalone_qs.order_by("expense_date"):
        amt = exp.amount_usd or Decimal("0.00")
        cat = exp.category
        label = (exp.description or "").strip() or (cat.name if cat else "Operating expense")
        suffix = str(exp.id).replace("-", "")[:7]
        rows.append(
            {
                "account": f"632{suffix}",
                "name": f"{label} ({exp.expense_no})",
                "curr": "USD",
                "tot_dr": amt,
                "tot_cr": Decimal("0.00"),
                "bal_dr": amt,
                "bal_cr": Decimal("0.00"),
            }
        )

    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    gross_profit = sales_total - cogs_total
    opex_sum = sum((r["tot_dr"] for r in rows if r["account"].startswith("632")), Decimal("0.00"))
    net_profit = gross_profit - opex_sum
    rows.append(profit_summary_row("Gross profit (Revenue − COGS)", gross_profit))
    rows.append(profit_summary_row("Net profit (Gross profit − OPEX)", net_profit))

    return render_or_pdf(
        request,
        "reporting/activity_trial_balance.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "period_label": period_label,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "bal_dr": bal_dr,
            "bal_cr": bal_cr,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "sales_total": sales_total,
            "cogs_total": cogs_total,
            "opex_total": opex_sum,
            "pdf_income_statement": True,
            "pdf_report_title": "Income Statement",
            "pdf_report_subtitle": "Posted sales revenue, cost of sales, and operating expenses (USD)",
            "pdf_account_range": "Accounts: 401 (Sales revenue), 501 (Cost of sales), 632 (Operating expenses)",
        },
        export_filename("Income_Statement", export_period_suffix(df, dt)),
    )


def clients_trial_balance(request):
    df, dt, _ = resolve_report_dates(request)
    q = (request.GET.get("q") or "").strip()
    clients = Client.objects.all().order_by("name_en")
    if q:
        clients = clients.filter(Q(name_en__icontains=q) | Q(client_code__icontains=q))
    day_before = (df - timedelta(days=1)) if df else None
    rows = []
    for client in clients:
        opening = client_ar_balance(client, day_before) if df else Decimal("0.00")
        debit, credit = _client_period_movement(client, df, dt)
        closing = opening + debit - credit
        if debit == 0 and credit == 0 and opening == 0 and closing == 0:
            continue
        inv_q = SalesInvoice.objects.filter(client=client, status__in=SalesInvoice.reporting_statuses())
        if df:
            inv_q = inv_q.filter(issue_date__gte=df)
        if dt:
            inv_q = inv_q.filter(issue_date__lte=dt)
        inv_n = inv_q.count()
        row_curr = inv_q.order_by("-issue_date").values_list("currency", flat=True).first() or "USD"
        bd, bc = _split_balance_dr_cr(closing)
        rows.append(
            {
                "account": f"411{client.client_code}"[:32],
                "name": client.name_en,
                "client_id": client.id,
                "client_code": client.client_code,
                "invoice_count": inv_n,
                "curr": row_curr,
                "opening_dr": _split_balance_dr_cr(opening)[0],
                "opening_cr": _split_balance_dr_cr(opening)[1],
                "tot_dr": debit,
                "tot_cr": credit,
                "closing": closing,
                "bal_dr": bd,
                "bal_cr": bc,
            }
        )
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    return render_or_pdf(
        request,
        "reporting/clients_trial_balance.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "q": q,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "bal_dr": bal_dr,
            "bal_cr": bal_cr,
            "pdf_report_title": "Clients Trial Balance",
            "pdf_report_subtitle": "Per-client debits, credits, and closing balance in the selected period",
            "pdf_account_range": "Client receivables (41 series — symbolic codes)",
        },
        export_filename("Clients_Trial_Balance", export_period_suffix(df, dt)),
    )


def suppliers_trial_balance(request):
    df, dt, _ = resolve_report_dates(request)
    q = (request.GET.get("q") or "").strip()
    suppliers = Supplier.objects.all().order_by("name")
    if q:
        suppliers = suppliers.filter(Q(name__icontains=q) | Q(supplier_code__icontains=q))
    day_before = (df - timedelta(days=1)) if df else None
    rows = []
    for supplier in suppliers:
        opening = supplier_ap_balance(supplier, day_before) if df else Decimal("0.00")
        debit, credit = _supplier_period_movement(supplier, df, dt)
        closing = opening + credit - debit
        if debit == 0 and credit == 0 and opening == 0 and closing == 0:
            continue
        bill_q = SupplierBill.objects.filter(supplier=supplier, status=SupplierBill.Status.POSTED)
        if df:
            bill_q = bill_q.filter(bill_date__gte=df)
        if dt:
            bill_q = bill_q.filter(bill_date__lte=dt)
        bill_n = bill_q.count()
        row_curr = bill_q.order_by("-bill_date").values_list("currency", flat=True).first() or "USD"
        bd, bc = _split_balance_dr_cr(closing)
        rows.append(
            {
                "account": f"211{supplier.supplier_code}"[:32],
                "name": supplier.name,
                "supplier_id": supplier.id,
                "supplier_code": supplier.supplier_code,
                "bill_count": bill_n,
                "curr": row_curr,
                "opening_dr": _split_balance_dr_cr(opening)[0],
                "opening_cr": _split_balance_dr_cr(opening)[1],
                "tot_dr": debit,
                "tot_cr": credit,
                "closing": closing,
                "bal_dr": bd,
                "bal_cr": bc,
            }
        )
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    return render_or_pdf(
        request,
        "reporting/suppliers_trial_balance.html",
        {
            "rows": rows,
            "date_from": df,
            "date_to": dt,
            "q": q,
            "tot_dr": tot_dr,
            "tot_cr": tot_cr,
            "bal_dr": bal_dr,
            "bal_cr": bal_cr,
            "pdf_report_title": "Suppliers Trial Balance",
            "pdf_report_subtitle": "Per-supplier debits, credits, and closing balance in the selected period",
            "pdf_account_range": "Trade payables (21 series — symbolic codes)",
        },
        export_filename("Suppliers_Trial_Balance", export_period_suffix(df, dt)),
    )


def _parse_report_dates(request):
    """Resolve date_from/date_to from month picker or custom range."""
    from calendar import monthrange

    month_str = (request.GET.get("month") or "").strip()
    df, dt, _ = resolve_report_dates(request)
    if month_str and len(month_str) == 7 and "-" in month_str:
        year, month = map(int, month_str.split("-", 1))
        df = date(year, month, 1)
        dt = date(year, month, monthrange(year, month)[1])
    return df, dt


def salesman_reports_home(request):
    employees = Employee.objects.filter(is_active=True).order_by("name")
    return render(
        request,
        "reporting/salesman_reports_home.html",
        {"employees": employees},
    )


def salesman_brief_report(request, employee_id):
    employee = get_object_or_404(Employee, pk=employee_id)
    df, dt = _parse_report_dates(request)
    report = build_brief_report(employee, df, dt)
    report["pdf_report_title"] = f"Brief Sales Report — {employee.name}"
    report["pdf_report_subtitle"] = "Summary of services, clients, revenue, and profit (USD)"
    return render_or_pdf(
        request,
        "reporting/salesman_brief_report.html",
        report,
        export_filename("Sales_Report_Brief", employee.name, export_period_suffix(df, dt)),
    )


def salesman_detailed_report(request, employee_id):
    employee = get_object_or_404(Employee, pk=employee_id)
    df, dt = _parse_report_dates(request)
    report = build_detailed_report(employee, df, dt)
    report["pdf_report_title"] = f"Detailed Sales Report — {employee.name}"
    report["pdf_report_subtitle"] = "Per-invoice selling, cost, and profit (USD)"
    return render_or_pdf(
        request,
        "reporting/salesman_detailed_report.html",
        report,
        export_filename("Sales_Report_Detailed", employee.name, export_period_suffix(df, dt)),
    )
