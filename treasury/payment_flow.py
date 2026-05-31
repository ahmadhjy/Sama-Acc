from django.db import transaction

from auditlog.models import DocumentEventLog
from auditlog.utils import log_audit, log_document_event
from treasury.allocation import auto_allocate_payment
from treasury.models import Payment


@transaction.atomic
def post_payment_and_allocate(payment: Payment, user) -> None:
    """Post a draft payment and auto-allocate to open invoices/bills."""
    if payment.status != Payment.Status.DRAFT:
        return
    payment.post(user)
    auto_allocate_payment(payment)
    log_document_event(DocumentEventLog.EventType.POSTED, payment, user)
    log_audit("POST_PAYMENT", payment, actor=user)
