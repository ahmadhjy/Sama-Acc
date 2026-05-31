from decimal import Decimal

from treasury.models import Payment


def payment_usd_amount(payment: Payment) -> Decimal:
    """USD equivalent for statements and AR/AP balances (matches invoice USD logic)."""
    if payment.currency == "USD":
        return payment.amount
    rate = payment.exchange_rate
    if rate is not None and rate > 0:
        return (payment.amount * rate).quantize(Decimal("0.01"))
    return payment.amount
