from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="money")
def money(value, places=2):
    """Format Decimal/number for display (e.g. 85276.40 instead of 85276.40000000)."""
    if value is None or value == "":
        return "—"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    places = int(places)
    quant = Decimal("1").scaleb(-places)
    return f"{d.quantize(quant):,.{places}f}"
