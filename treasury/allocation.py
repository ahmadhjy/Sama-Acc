from decimal import Decimal

from django.db import transaction

from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, Payment


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
            allocated = sum((a.allocated_amount for a in inv.allocations.all()), Decimal("0.00"))
            due = inv.grand_total - allocated
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
            allocated = sum((a.allocated_amount for a in bill.allocations.all()), Decimal("0.00"))
            due = bill.grand_total - allocated
            if due <= 0:
                continue
            take = min(remaining, due)
            APAllocation.objects.create(payment=payment, supplier_bill=bill, allocated_amount=take)
            remaining -= take
