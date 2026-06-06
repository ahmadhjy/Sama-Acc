from datetime import date, datetime


def sort_statement_rows(rows):
    """Oldest first; stable tie-break by created time then id."""

    def _key(row):
        d = row.get("date") or date.min
        seq = row.get("sort_seq")
        if isinstance(seq, datetime):
            seq_val = seq
        elif seq is not None:
            seq_val = seq
        else:
            seq_val = datetime.min
        return (d, seq_val, row.get("sort_id") or "")

    rows.sort(key=_key)
    return rows
