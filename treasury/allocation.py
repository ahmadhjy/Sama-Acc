from decimal import Decimal

from django.db import transaction

from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, Payment


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
