from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

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


@register.filter(name="truncate_detail")
def truncate_detail(value, limit=42):
    """Truncate long table text; full value available on hover via title."""
    text = str(value or "").strip() or "—"
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 42
    if len(text) <= limit:
        return text
    short = text[: limit - 1].rstrip() + "…"
    return mark_safe(f'<span class="cell-detail" title="{escape(text)}">{escape(short)}</span>')
