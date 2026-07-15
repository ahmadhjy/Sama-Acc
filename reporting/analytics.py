from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from accounts_core.models import Employee, Supplier
from reporting.date_ranges import resolve_report_dates
from reporting.invoice_pl import period_cogs_usd, period_opex_by_category, period_opex_usd, period_revenue_usd
from reporting.payment_amounts import payment_usd_amount
from reporting.period_movements import (
    client_ar_balances_as_of,
    supplier_ap_balances_as_of,
    supplier_period_movements,
)
from sales.models import SalesInvoice, SalesInvoiceLine, SalesInvoiceScheduledPayment
from treasury.allocation import invoice_collectible_remaining
from treasury.models import Payment


def build_dashboard_analytics(request, *, revenue=None, cogs=None, opex_total=None):
    date_from, date_to, period_label = resolve_report_dates(request)
    today = date.today()

    if revenue is None:
        revenue = period_revenue_usd(date_from, date_to)
    if cogs is None:
        cogs = period_cogs_usd(date_from, date_to)
    if opex_total is None:
        opex_total = period_opex_usd(date_from, date_to)
    gross_profit = revenue - cogs
    net_profit = gross_profit - opex_total

    # Closing AR/AP as of today (not period-filtered).
    ar_by_client = client_ar_balances_as_of(today)
    ap_by_supplier = supplier_ap_balances_as_of(today)
    total_ar = sum(ar_by_client.values(), Decimal("0.00"))
    total_ap = sum(ap_by_supplier.values(), Decimal("0.00"))

    payments_in = Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.IN)
    payments_out = Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.OUT)
    if date_from:
        payments_in = payments_in.filter(date__gte=date_from)
        payments_out = payments_out.filter(date__gte=date_from)
    if date_to:
        payments_in = payments_in.filter(date__lte=date_to)
        payments_out = payments_out.filter(date__lte=date_to)
    cash_in = payments_in.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    treasury_cash_out = payments_out.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    # Cash flow Out = treasury money-out + period OPEX (OPEX stays its own KPI/chart).
    cash_out = treasury_cash_out + opex_total

    from treasury.allocation import _client_invoices_ordered, _collectible_open_by_invoice

    receivables_due = []
    collectible_cache: dict = {}
    for inv in (
        SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
        .select_related("client")
        .prefetch_related("allocations")
        .order_by("due_date", "issue_date")
    ):
        client_id = inv.client_id
        if ar_by_client.get(client_id, Decimal("0.00")) <= 0:
            continue
        if client_id not in collectible_cache:
            collectible_cache[client_id] = _collectible_open_by_invoice(_client_invoices_ordered(inv.client))
        allocated = sum((a.allocated_amount for a in inv.allocations.all()), Decimal("0.00"))
        total = inv.grand_total_usd if inv.grand_total_usd is not None else (inv.grand_total or Decimal("0.00"))
        remaining = invoice_collectible_remaining(inv, collectible_cache=collectible_cache[client_id])
        if remaining <= 0:
            continue
        due = inv.due_date or inv.issue_date
        days_until = (due - today).days
        is_overdue = today > due and remaining > 0
        receivables_due.append(
            {
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
        )
    receivables_due.sort(key=lambda x: (0 if x["is_overdue"] else 1, x["due_date"]))
    overdue_client_payments = [r for r in receivables_due if r["is_overdue"]]
    overdue_client_payments.sort(key=lambda x: x["due_date"])

    sell_expr = ExpressionWrapper(
        F("qty") * Coalesce(F("sell_price_usd"), Value(Decimal("0.00")))
        - Coalesce(F("line_discount_usd"), Value(Decimal("0.00"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    cost_expr = ExpressionWrapper(
        F("qty") * Coalesce(F("cost_price_usd"), Value(Decimal("0.00"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    salesman_lines = SalesInvoiceLine.objects.filter(
        line_employee__role=Employee.EmployeeRole.SALES,
        invoice__status__in=SalesInvoice.reporting_statuses(),
    ).annotate(line_date=Coalesce("service_date", "invoice__issue_date"))
    if date_from:
        salesman_lines = salesman_lines.filter(line_date__gte=date_from)
    if date_to:
        salesman_lines = salesman_lines.filter(line_date__lte=date_to)
    salesman_by_emp = {
        row["line_employee_id"]: row
        for row in salesman_lines.values("line_employee_id").annotate(sales=Sum(sell_expr), cost=Sum(cost_expr))
    }
    salesman_stats = []
    for emp in Employee.objects.filter(role=Employee.EmployeeRole.SALES, id__in=salesman_by_emp.keys()).order_by("name"):
        row = salesman_by_emp[emp.id]
        sales = row["sales"] or Decimal("0.00")
        cost = row["cost"] or Decimal("0.00")
        profit = sales - cost
        if sales == 0 and profit == 0:
            continue
        salesman_stats.append({"employee": emp, "sales": sales, "profit": profit, "cost": cost})
    salesman_stats.sort(key=lambda x: x["profit"], reverse=True)

    purchase_by_sup = {sid: credit for sid, (_d, credit) in supplier_period_movements(date_from, date_to).items()}
    supplier_stats = []
    for sid in set(ap_by_supplier) | set(purchase_by_sup):
        balance = ap_by_supplier.get(sid, Decimal("0.00"))
        purchases = purchase_by_sup.get(sid, Decimal("0.00"))
        if balance == 0 and purchases == 0:
            continue
        supplier_stats.append({"supplier_id": sid, "balance": balance, "purchases": purchases})
    supplier_stats.sort(key=lambda x: x["balance"], reverse=True)
    top_supplier_ids = [s["supplier_id"] for s in supplier_stats[:15]]
    supplier_objs = Supplier.objects.in_bulk(top_supplier_ids)
    supplier_stats = [
        {
            "supplier": supplier_objs[s["supplier_id"]],
            "balance": s["balance"],
            "purchases": s["purchases"],
        }
        for s in supplier_stats[:15]
        if s["supplier_id"] in supplier_objs
    ]

    # Monthly revenue trend (SOA-aligned) within the selected period — one SQL pass.
    chart_from, chart_to = date_from, date_to
    if not chart_from or not chart_to:
        chart_to = today
        chart_from = date(today.year, today.month, 1)
        for _ in range(5):
            if chart_from.month == 1:
                chart_from = date(chart_from.year - 1, 12, 1)
            else:
                chart_from = date(chart_from.year, chart_from.month - 1, 1)

    month_totals = {}
    month_lines = SalesInvoiceLine.objects.filter(
        invoice__status__in=SalesInvoice.reporting_statuses(),
    ).annotate(line_date=Coalesce("service_date", "invoice__issue_date"))
    if chart_from:
        month_lines = month_lines.filter(line_date__gte=chart_from)
    if chart_to:
        month_lines = month_lines.filter(line_date__lte=chart_to)
    for row in (
        month_lines.annotate(month=TruncMonth("line_date"))
        .values("month")
        .annotate(total=Sum(sell_expr))
    ):
        if row["month"]:
            raw = row["month"]
            if hasattr(raw, "date") and callable(raw.date):
                raw = raw.date()
            key = date(raw.year, raw.month, 1)
            month_totals[key] = month_totals.get(key, Decimal("0.00")) + (row["total"] or Decimal("0.00"))

    out_pays = Payment.objects.filter(
        party_type=Payment.PartyType.CLIENT,
        status=Payment.Status.POSTED,
        direction=Payment.Direction.OUT,
    )
    if chart_from:
        out_pays = out_pays.filter(date__gte=chart_from)
    if chart_to:
        out_pays = out_pays.filter(date__lte=chart_to)
    for pay in out_pays.only("date", "amount", "currency", "exchange_rate"):
        key = date(pay.date.year, pay.date.month, 1)
        month_totals[key] = month_totals.get(key, Decimal("0.00")) + payment_usd_amount(pay)

    monthly_revenue = []
    y, m = chart_from.year, chart_from.month
    while date(y, m, 1) <= chart_to and len(monthly_revenue) < 12:
        m_start = date(y, m, 1)
        monthly_revenue.append(
            {"label": m_start.strftime("%b %Y"), "value": float(month_totals.get(m_start, Decimal("0.00")))}
        )
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    max_month = max((m["value"] for m in monthly_revenue), default=1) or 1

    top_salesmen = salesman_stats[:8]
    chart_salesman_labels = [s["employee"].name for s in top_salesmen]
    chart_salesman_sales = [float(s["sales"]) for s in top_salesmen]
    chart_salesman_profit = [float(s["profit"]) for s in top_salesmen]
    chart_salesman_ids = [str(s["employee"].id) for s in top_salesmen]

    top_suppliers = supplier_stats[:8]
    chart_supplier_labels = [s["supplier"].name for s in top_suppliers]
    chart_supplier_balances = [float(s["balance"]) for s in top_suppliers]

    opex_by_cat = list(period_opex_by_category(date_from, date_to).order_by("-total")[:6])
    chart_opex_labels = [
        (r["category__name"] or r["category__code"] or "Uncategorized") for r in opex_by_cat
    ]
    chart_opex_values = [float(r["total"] or 0) for r in opex_by_cat]

    # Reuse collectible + AR caches from the receivables loop for aging chart.
    ar_buckets = {
        "current": Decimal("0"),
        "b0_30": Decimal("0"),
        "b31_60": Decimal("0"),
        "b61_90": Decimal("0"),
        "b90": Decimal("0"),
    }
    for row in receivables_due:
        due = row["due_date"]
        remaining = row["remaining"]
        days = (due - today).days
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

    # Management payment plan rows (independent of treasury allocations).
    schedule_status = (request.GET.get("schedule_status") or "unpaid").strip().lower()
    if schedule_status not in ("unpaid", "paid", "all"):
        schedule_status = "unpaid"
    schedule_qs = (
        SalesInvoiceScheduledPayment.objects.filter(
            invoice__status__in=SalesInvoice.reporting_statuses(),
        )
        .select_related("invoice", "invoice__client")
        .order_by("due_date", "invoice__invoice_no")
    )
    if schedule_status == "unpaid":
        schedule_qs = schedule_qs.filter(is_paid=False)
    elif schedule_status == "paid":
        schedule_qs = schedule_qs.filter(is_paid=True)
    scheduled_client_payments = []
    for pay in schedule_qs[:200]:
        due = pay.due_date
        days_until = (due - today).days if due else 0
        if pay.is_paid:
            row_status = "paid"
        elif days_until < 0:
            row_status = "overdue"
        elif days_until == 0:
            row_status = "today"
        else:
            row_status = "upcoming"
        scheduled_client_payments.append(
            {
                "id": pay.id,
                "client_name": pay.invoice.client.name_en if pay.invoice.client_id else "—",
                "invoice_id": pay.invoice_id,
                "invoice_no": pay.invoice.invoice_no,
                "amount": pay.amount,
                "currency": pay.invoice.currency,
                "due_date": due,
                "is_paid": pay.is_paid,
                "status": row_status,
                "days_until": days_until,
            }
        )

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
        "treasury_cash_out": treasury_cash_out,
        "receivables_due": receivables_due[:20],
        "overdue_client_payments": overdue_client_payments,
        "overdue_count": len(overdue_client_payments),
        "due_today_count": sum(1 for r in receivables_due if r["status"] == "today"),
        "scheduled_client_payments": scheduled_client_payments,
        "schedule_status": schedule_status,
        "schedule_unpaid_count": SalesInvoiceScheduledPayment.objects.filter(
            invoice__status__in=SalesInvoice.reporting_statuses(),
            is_paid=False,
        ).count(),
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
