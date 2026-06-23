"""Human-readable, filesystem-safe names for PDF/Excel exports."""

import re
from datetime import date


def slugify_filename_part(value, max_len=50):
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "_", s)
    return s[:max_len].strip("_")


def export_filename(*parts, ext="pdf"):
    bits = [slugify_filename_part(p) for p in parts if p is not None and str(p).strip()]
    name = "_".join(bits) if bits else "export"
    return f"{name}.{ext.lstrip('.')}"


def export_period_suffix(date_from=None, date_to=None):
    if isinstance(date_from, date) and isinstance(date_to, date):
        if date_from.year == date_to.year and date_from.month == 1 and date_to.month == 12:
            if date_from.day == 1 and date_to.day == 31:
                return str(date_from.year)
        return f"{date_from.isoformat()}_to_{date_to.isoformat()}"
    if isinstance(date_from, date):
        return f"from_{date_from.isoformat()}"
    if isinstance(date_to, date):
        return f"until_{date_to.isoformat()}"
    return ""
