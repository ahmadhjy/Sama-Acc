from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from accounts_core.models import Client, Employee, Supplier
from expenses.models import OperatingExpense
from purchases.models import SupplierBill
from reporting.balances import client_ar_balance, supplier_ap_balance, supplier_line_purchases
from reporting.date_ranges import resolve_report_dates
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment


def _lines_cost_usd(date_from=None, date_to=None):
    qs = SalesInvoiceLine.objects.filter(invoice__status__in=SalesInvoice.reporting_statuses())
    if date_from:
        qs = qs.filter(service_date__gte=date_from)
    if date_to:
        qs = qs.filter(service_date__lte=date_to)
    total = Decimal("0.00")
    for line in qs.only("qty", "cost_price_usd"):
        total += line.line_cost_amount_usd()
    return total


def build_dashboard_analytics(request):
    date_from, date_to, period_label = resolve_report_dates(request)
    today = date.today()

    inv_q = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
    if date_from:
        inv_q = inv_q.filter(issue_date__gte=date_from)
    if date_to:
        inv_q = inv_q.filter(issue_date__lte=date_to)

    revenue = inv_q.aggregate(t=Sum("grand_total_usd"))["t"] or Decimal("0.00")
    cogs = _lines_cost_usd(date_from, date_to)
    opex = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED)
    if date_from:
        opex = opex.filter(expense_date__gte=date_from)
    if date_to:
        opex = opex.filter(expense_date__lte=date_to)
    opex_total = opex.aggregate(t=Sum("amount_usd"))["t"] or Decimal("0.00")
    gross_profit = revenue - cogs
    net_profit = gross_profit - opex_total

    total_ar = Decimal("0.00")
    for client in Client.objects.all():
        total_ar += client_ar_balance(client, today)

    total_ap = Decimal("0.00")
    for supplier in Supplier.objects.all():
        total_ap += supplier_ap_balance(supplier, today)

    payments_in = Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.IN)
    payments_out = Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.OUT)
    if date_from:
        payments_in = payments_in.filter(date__gte=date_from)
        payments_out = payments_out.filter(date__gte=date_from)
    if date_to:
        payments_in = payments_in.filter(date__lte=date_to)
        payments_out = payments_out.filter(date__lte=date_to)
    cash_in = payments_in.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    cash_out = payments_out.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

    receivables_due = []
    for inv in (
        SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
        .select_related("client")
        .order_by("due_date", "issue_date")
    ):
        allocated = sum((a.allocated_amount for a in inv.allocations.all()), Decimal("0.00"))
        total = inv.grand_total_usd if inv.grand_total_usd is not None else (inv.grand_total or Decimal("0.00"))
        remaining = total - allocated
        if remaining <= 0:
            continue
        due = inv.due_date or inv.issue_date
        days_until = (due - today).days
        is_overdue = today > due and remaining > 0
        row = {
            "invoice": inv,
            "client_name": inv.client.name_en,
            "invoice_no": inv.invoice_no,
            "total": total,
            "paid": allocated,
            "remaining": remaining,
            "currency": inv.currency,
            "due_date": due,
            "days_until": days_until,
            "status": "overdue" if is_overdue else ("today" if days_until == 0 else "upcoming"),
            "is_overdue": is_overdue,
        }
        receivables_due.append(row)
    receivables_due.sort(key=lambda x: (0 if x["is_overdue"] else 1, x["due_date"]))
    overdue_client_payments = [r for r in receivables_due if r["is_overdue"]]
    overdue_client_payments.sort(key=lambda x: x["due_date"])

    salesman_stats = []
    for emp in Employee.objects.filter(role=Employee.EmployeeRole.SALES).order_by("name"):
        lines = SalesInvoiceLine.objects.filter(
            line_employee=emp,
            invoice__status__in=SalesInvoice.reporting_statuses(),
        )
        if date_from:
            lines = lines.filter(service_date__gte=date_from)
        if date_to:
            lines = lines.filter(service_date__lte=date_to)
        sales = Decimal("0.00")
        cost = Decimal("0.00")
        for line in lines:
            sales += line.line_selling_amount_usd()
            cost += line.line_cost_amount_usd()
        profit = sales - cost
        if sales == 0 and profit == 0:
            continue
        salesman_stats.append(
            {"employee": emp, "sales": sales, "profit": profit, "cost": cost}
        )
    salesman_stats.sort(key=lambda x: x["profit"], reverse=True)

    supplier_stats = []
    for sup in Supplier.objects.order_by("name"):
        balance = supplier_ap_balance(sup, today)
        purchases = supplier_line_purchases(sup, date_from, date_to)
        if balance == 0 and purchases == 0:
            continue
        supplier_stats.append(
            {
                "supplier": sup,
                "balance": balance,
                "purchases": purchases,
            }
        )
    supplier_stats.sort(key=lambda x: x["balance"], reverse=True)

    monthly_revenue = []
    y, m = today.year, today.month
    for offset in range(5, -1, -1):
        mm = m - offset
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        m_start = date(yy, mm, 1)
        if mm == 12:
            m_end = date(yy, 12, 31)
        else:
            m_end = date(yy, mm + 1, 1) - timedelta(days=1)
        m_rev = (
            SalesInvoice.objects.filter(
                status__in=SalesInvoice.reporting_statuses(),
                issue_date__gte=m_start,
                issue_date__lte=m_end,
            ).aggregate(t=Sum("grand_total_usd"))["t"]
            or Decimal("0.00")
        )
        monthly_revenue.append({"label": m_start.strftime("%b %Y"), "value": float(m_rev)})

    max_month = max((m["value"] for m in monthly_revenue), default=1) or 1

    top_salesmen = salesman_stats[:8]
    chart_salesman_labels = [s["employee"].name for s in top_salesmen]
    chart_salesman_sales = [float(s["sales"]) for s in top_salesmen]
    chart_salesman_profit = [float(s["profit"]) for s in top_salesmen]
    chart_salesman_ids = [str(s["employee"].id) for s in top_salesmen]

    top_suppliers = supplier_stats[:8]
    chart_supplier_labels = [s["supplier"].name for s in top_suppliers]
    chart_supplier_balances = [float(s["balance"]) for s in top_suppliers]

    opex_by_cat = (
        opex.values("category__name", "category__code")
        .annotate(total=Sum("amount_usd"))
        .order_by("-total")[:6]
    )
    chart_opex_labels = [
        (r["category__name"] or r["category__code"] or "Uncategorized") for r in opex_by_cat
    ]
    chart_opex_values = [float(r["total"] or 0) for r in opex_by_cat]

    ar_buckets = {"current": Decimal("0"), "b0_30": Decimal("0"), "b31_60": Decimal("0"), "b61_90": Decimal("0"), "b90": Decimal("0")}
    today_d = today
    for inv in SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses()).select_related("client"):
        allocated = sum((a.allocated_amount for a in inv.allocations.all()), Decimal("0.00"))
        remaining = (inv.grand_total_usd if inv.grand_total_usd is not None else (inv.grand_total or Decimal("0.00"))) - allocated
        if remaining <= 0:
            continue
        due = inv.due_date or inv.issue_date
        days = (due - today_d).days
        if days > 0:
            ar_buckets["current"] += remaining
        elif days >= -30:
            ar_buckets["b0_30"] += remaining
        elif days >= -60:
            ar_buckets["b31_60"] += remaining
        elif days >= -90:
            ar_buckets["b61_90"] += remaining
        else:
            ar_buckets["b90"] += remaining
    chart_ar_aging_labels = ["Not due", "0–30 days", "31–60", "61–90", "90+"]
    chart_ar_aging_values = [
        float(ar_buckets["current"]),
        float(ar_buckets["b0_30"]),
        float(ar_buckets["b31_60"]),
        float(ar_buckets["b61_90"]),
        float(ar_buckets["b90"]),
    ]

    return {
        "date_from": date_from,
        "date_to": date_to,
        "period_label": period_label,
        "revenue": revenue,
        "cogs": cogs,
        "opex": opex_total,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "total_ar": total_ar,
        "total_ap": total_ap,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "cash_net": cash_in - cash_out,
        "receivables_due": receivables_due[:20],
        "overdue_client_payments": overdue_client_payments,
        "overdue_count": len(overdue_client_payments),
        "due_today_count": sum(1 for r in receivables_due if r["status"] == "today"),
        "salesman_stats": salesman_stats[:15],
        "supplier_stats": supplier_stats[:15],
        "monthly_revenue": monthly_revenue,
        "max_month_revenue": max_month,
        "chart_monthly_labels": [m["label"] for m in monthly_revenue],
        "chart_monthly_values": [m["value"] for m in monthly_revenue],
        "chart_salesman_labels": chart_salesman_labels,
        "chart_salesman_sales": chart_salesman_sales,
        "chart_salesman_profit": chart_salesman_profit,
        "chart_salesman_ids": chart_salesman_ids,
        "chart_supplier_labels": chart_supplier_labels,
        "chart_supplier_balances": chart_supplier_balances,
        "chart_cash_in": float(cash_in),
        "chart_cash_out": float(cash_out),
        "chart_revenue": float(revenue),
        "chart_cogs": float(cogs),
        "chart_opex": float(opex_total),
        "chart_gross_profit": float(gross_profit),
        "chart_net_profit": float(net_profit),
        "chart_total_ar": float(total_ar),
        "chart_total_ap": float(total_ap),
        "chart_opex_labels": chart_opex_labels,
        "chart_opex_values": chart_opex_values,
        "chart_ar_aging_labels": chart_ar_aging_labels,
        "chart_ar_aging_values": chart_ar_aging_values,
    }
