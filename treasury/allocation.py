from decimal import Decimal

from django.db import transaction

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, Payment


def _invoice_open_amount(invoice: SalesInvoice) -> Decimal:
    allocated = sum((a.allocated_amount for a in invoice.allocations.all()), Decimal("0.00"))
    total = invoice.grand_total_usd if invoice.grand_total_usd is not None else (invoice.grand_total or Decimal("0.00"))
    return total - allocated


def _bill_open_amount(bill: SupplierBill) -> Decimal:
    allocated = sum((a.allocated_amount for a in bill.allocations.all()), Decimal("0.00"))
    return (bill.grand_total or Decimal("0.00")) - allocated


def _allocation_rows(payment: Payment):
    rows = []
    for alloc in payment.ar_allocations.all():
        rows.append(alloc)
    for alloc in payment.ap_allocations.all():
        rows.append(alloc)
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows


def trim_allocations_to_fit(payment: Payment) -> None:
    """Reduce or remove allocations when payment amount is lowered below allocated total."""
    excess = payment.allocated_amount - payment.amount
    if excess <= 0:
        return
    for alloc in _allocation_rows(payment):
        if excess <= 0:
            break
        if alloc.allocated_amount <= excess:
            excess -= alloc.allocated_amount
            alloc.delete()
        else:
            alloc.allocated_amount -= excess
            alloc.save(update_fields=["allocated_amount"])
            excess = Decimal("0.00")


def clear_payment_allocations(payment: Payment) -> None:
    payment.ar_allocations.all().delete()
    payment.ap_allocations.all().delete()


@transaction.atomic
def auto_allocate_payment(payment: Payment) -> None:
    """Allocate posted payment to oldest open invoices (AR) or bills (AP)."""
    if payment.status != Payment.Status.POSTED:
        return

    if payment.direction == Payment.Direction.IN and payment.party_type == Payment.PartyType.CLIENT and payment.client_id:
        remaining = payment.remaining_amount
        if remaining <= 0:
            return
        invoices = (
            SalesInvoice.objects.filter(client=payment.client, status__in=SalesInvoice.reporting_statuses())
            .order_by("due_date", "issue_date", "created_at")
            .prefetch_related("allocations")
        )
        for inv in invoices:
            if remaining <= 0:
                break
            due = _invoice_open_amount(inv)
            if due <= 0:
                continue
            take = min(remaining, due)
            ARAllocation.objects.create(payment=payment, sales_invoice=inv, allocated_amount=take)
            remaining -= take
        return

    if payment.direction == Payment.Direction.OUT and payment.party_type == Payment.PartyType.SUPPLIER and payment.supplier_id:
        remaining = payment.remaining_amount
        if remaining <= 0:
            return
        bills = (
            SupplierBill.objects.filter(supplier=payment.supplier, status=SupplierBill.Status.POSTED)
            .order_by("due_date", "bill_date", "created_at")
            .prefetch_related("allocations")
        )
        for bill in bills:
            if remaining <= 0:
                break
            due = _bill_open_amount(bill)
            if due <= 0:
                continue
            take = min(remaining, due)
            APAllocation.objects.create(payment=payment, supplier_bill=bill, allocated_amount=take)
            remaining -= take


@transaction.atomic
def rebuild_client_ar_allocations(client: Client | None = None) -> int:
    """Clear and rebuild client payment allocations oldest due-date first."""
    clients = Client.objects.filter(pk=client.pk) if client else Client.objects.all()
    rebuilt = 0
    for party in clients:
        ARAllocation.objects.filter(sales_invoice__client=party).delete()
        payments = Payment.objects.filter(
            client=party,
            party_type=Payment.PartyType.CLIENT,
            direction=Payment.Direction.IN,
            status=Payment.Status.POSTED,
        ).order_by("date", "created_at", "receipt_no")
        for payment in payments:
            auto_allocate_payment(payment)
            rebuilt += 1
    return rebuilt


@transaction.atomic
def rebuild_supplier_ap_allocations(supplier: Supplier | None = None) -> int:
    """Clear and rebuild supplier payment allocations oldest due-date first."""
    suppliers = Supplier.objects.filter(pk=supplier.pk) if supplier else Supplier.objects.all()
    rebuilt = 0
    for party in suppliers:
        APAllocation.objects.filter(supplier_bill__supplier=party).delete()
        payments = Payment.objects.filter(
            supplier=party,
            party_type=Payment.PartyType.SUPPLIER,
            direction=Payment.Direction.OUT,
            status=Payment.Status.POSTED,
        ).order_by("date", "created_at", "receipt_no")
        for payment in payments:
            auto_allocate_payment(payment)
            rebuilt += 1
    return rebuilt
