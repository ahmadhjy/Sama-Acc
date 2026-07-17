from decimal import Decimal

from django.db import transaction

from auditlog.models import DocumentEventLog
from auditlog.utils import log_audit, log_document_event
from treasury.allocation import auto_allocate_payment, clear_payment_allocations, trim_allocations_to_fit
from treasury.legacy_payment_sync import remove_ledger_for_payment, sync_ledger_from_payment
from treasury.models import Payment


@transaction.atomic
def post_payment_and_allocate(payment: Payment, user) -> None:
    """Post a draft payment and auto-allocate to open invoices/bills."""
    if payment.status != Payment.Status.DRAFT:
        return
    payment.post(user)
    auto_allocate_payment(payment)
    sync_ledger_from_payment(payment)
    log_document_event(DocumentEventLog.EventType.POSTED, payment, user)
    log_audit("POST_PAYMENT", payment, actor=user)


@transaction.atomic
def sync_posted_payment_after_edit(
    payment: Payment,
    user,
    *,
    party_changed: bool,
    old_supplier_id=None,
) -> None:
    """Keep allocations and imported supplier ledger rows consistent after editing a posted payment."""
    if payment.status != Payment.Status.POSTED:
        return
    if payment.amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    before_allocated = payment.allocated_amount
    if party_changed:
        clear_payment_allocations(payment)
    elif payment.allocated_amount > payment.amount:
        trim_allocations_to_fit(payment)

    auto_allocate_payment(payment)
    payment.refresh_from_db()
    sync_ledger_from_payment(payment, old_supplier_id=old_supplier_id)
    log_document_event(
        DocumentEventLog.EventType.UPDATED_DRAFT,
        payment,
        user,
        {
            "edited_while_status": payment.status,
            "party_changed": party_changed,
            "allocated_before": str(before_allocated),
            "allocated_after": str(payment.allocated_amount),
            "remaining_after": str(payment.remaining_amount),
        },
    )
    log_audit(
        "UPDATE_PAYMENT",
        payment,
        actor=user,
        before={"allocated": str(before_allocated)},
        after={
            "amount": str(payment.amount),
            "allocated": str(payment.allocated_amount),
            "remaining": str(payment.remaining_amount),
        },
    )
