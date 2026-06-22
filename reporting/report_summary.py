"""Reporting summary metrics (former reports home)."""

from decimal import Decimal

from django.db.models import Sum

from reporting.date_ranges import resolve_report_dates
from expenses.models import OperatingExpense
from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import Payment


def build_report_summary(request):
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

    posted_invoices_total = inv_q.aggregate(total=Sum("grand_total_usd"))["total"] or Decimal("0.00")
    posted_bills_total = bill_q.aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")
    posted_payments_total = pay_q.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    posted_cogs_total = cogs_q.aggregate(total=Sum("lines__cost_amount"))["total"] or Decimal("0.00")

    opex_q = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED)
    if df:
        opex_q = opex_q.filter(expense_date__gte=df)
    if dt:
        opex_q = opex_q.filter(expense_date__lte=dt)
    total_opex = opex_q.aggregate(total=Sum("amount_usd"))["total"] or Decimal("0.00")

    net_profit_estimate = posted_invoices_total - posted_cogs_total - total_opex
    gross_margin_estimate = posted_invoices_total - posted_bills_total

    return {
        "posted_invoices_total": posted_invoices_total,
        "posted_bills_total": posted_bills_total,
        "posted_payments_total": posted_payments_total,
        "posted_cogs_total": posted_cogs_total,
        "total_opex": total_opex,
        "gross_margin_estimate": gross_margin_estimate,
        "net_profit_estimate": net_profit_estimate,
        "chart_summary_labels": ["Sales", "Purchases", "COGS", "OPEX", "Net profit"],
        "chart_summary_values": [
            float(posted_invoices_total),
            float(posted_bills_total),
            float(posted_cogs_total),
            float(total_opex),
            float(net_profit_estimate),
        ],
    }
