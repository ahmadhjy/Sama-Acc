from decimal import Decimal


def annotate_client_statement_rows(rows):
    """Oldest-first rows with running balance (positive = client owes us)."""
    running = Decimal("0.00")
    total_dr = Decimal("0.00")
    total_cr = Decimal("0.00")
    for row in rows:
        total_dr += row["debit"]
        total_cr += row["credit"]
        running = running + row["debit"] - row["credit"]
        row["running_balance"] = running
    return rows, total_dr, total_cr, running


def annotate_supplier_statement_rows(rows):
    """Oldest-first rows; balance shown negative when we owe the supplier."""
    running = Decimal("0.00")
    total_dr = Decimal("0.00")
    total_cr = Decimal("0.00")
    for row in rows:
        total_dr += row["debit"]
        total_cr += row["credit"]
        running = running + row["credit"] - row["debit"]
        row["running_balance"] = -running
    return rows, total_dr, total_cr, -running
