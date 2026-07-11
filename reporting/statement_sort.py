from datetime import date, datetime, time

from django.conf import settings
from django.utils import timezone


def _normalize_sort_seq(seq):
    if isinstance(seq, datetime):
        dt = seq
    elif isinstance(seq, date):
        dt = datetime.combine(seq, time.min)
    elif seq is None:
        dt = datetime.min
    else:
        return seq

    if settings.USE_TZ and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    if not settings.USE_TZ and timezone.is_aware(dt):
        return timezone.make_naive(dt, timezone.get_current_timezone())
    return dt


def sort_statement_rows(rows):
    """Oldest first; stable tie-break by created time then id."""

    def _key(row):
        d = row.get("date") or date.min
        return (d, _normalize_sort_seq(row.get("sort_seq")), row.get("sort_id") or "")

    rows.sort(key=_key)
    return rows
